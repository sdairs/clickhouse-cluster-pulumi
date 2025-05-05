"""Pulumi AWS ClickHouse Cluster Automation"""

import pulumi
import pulumi_aws as aws
import re
import os

# Configurable parameters
config = pulumi.Config()
prefix = config.get('prefix') or 'clickhouse'
cluster_size = config.get_int('cluster_size') or 3
instance_type = config.get('instance_type') or 'm6i.4xlarge'

# Use user-specified AMI
ami_id = "ami-04f167a56786e4b09"

# Optional: dev ClickHouse URL
dev_clickhouse_url = config.get('dev_clickhouse_url')

# Installing ClickHouse user data
def get_user_data(dev_url=None):
    if not dev_url:
        # Default ClickHouse install
        return """#!/bin/bash
set -e
curl https://clickhouse.com/ | sh
"""
    # Parse base URL and version
    # Example: https://.../build_amd_release/clickhouse-server_25.4.1.1_amd64.deb
    match = re.match(r"(.*/)(clickhouse-server_([\d.]+)_amd64\.deb)", dev_url)
    if not match:
        raise Exception("Invalid dev_clickhouse_url format")
    base_url, server_file, version = match.groups()
    files = [
        f"clickhouse-common-static_{version}_amd64.deb",
        f"clickhouse-client_{version}_amd64.deb",
        f"clickhouse-server_{version}_amd64.deb",
    ]
    download_cmds = "\n".join([
        f"wget {base_url}{fname}" for fname in files
    ])
    install_cmds = "dpkg -i clickhouse-common-static_{v}_amd64.deb && dpkg -i clickhouse-client_{v}_amd64.deb && dpkg -i clickhouse-server_{v}_amd64.deb".replace('{v}', version)
    return f"""#!/bin/bash
set -e
apt-get update
apt-get install -y wget
cd /tmp
{download_cmds}
{install_cmds}
"""

# Create EC2 instances with cluster config
instances = []
private_ips = []

# Helper to render the cluster config XML for a node
def render_cluster_config(node_idx, all_ips):
    shards = []
    # Localhost shard
    shards.append(f"""
        <shard>
            <replica>
                <host>localhost</host>
                <port>9000</port>
                <user>default</user>
                <password>{prefix}</password>
            </replica>
        </shard>""")
    # Other nodes' IPs
    for idx, ip in enumerate(all_ips):
        if idx == node_idx:
            continue
        shards.append(f"""
        <shard>
            <replica>
                <host>{ip}</host>
                <port>9000</port>
                <user>default</user>
                <password>{prefix}</password>
            </replica>
        </shard>""")
    return f"""<clickhouse>
<remote_servers>
    <default>
{''.join(shards)}
    </default>
</remote_servers>
</clickhouse>
"""

# Prepare instance names
instance_names = [f"{prefix}-node-{i}" for i in range(cluster_size)]

# --- Networking setup ---
# Configurable VPC and Subnet CIDRs
internal_vpc_cidr = config.get('internal_vpc_cidr') or '10.10.0.0/16'
internal_subnet_cidr = config.get('internal_subnet_cidr') or '10.10.0.0/24'

# Create a VPC
vpc = aws.ec2.Vpc(
    f"{prefix}-vpc",
    cidr_block=internal_vpc_cidr,
    enable_dns_support=True,
    enable_dns_hostnames=True,
    tags={"Name": f"{prefix}-vpc"}
)

# Create a subnet
subnet = aws.ec2.Subnet(
    f"{prefix}-subnet",
    vpc_id=vpc.id,
    cidr_block=internal_subnet_cidr,
    map_public_ip_on_launch=True,
    tags={"Name": f"{prefix}-subnet"}
)

# --- Internet Gateway and Route Table for public access ---
igw = aws.ec2.InternetGateway(
    f"{prefix}-igw",
    vpc_id=vpc.id,
    tags={"Name": f"{prefix}-igw"}
)

route_table = aws.ec2.RouteTable(
    f"{prefix}-rt",
    vpc_id=vpc.id,
    routes=[
        {"cidr_block": internal_vpc_cidr, "gateway_id": "local"},
        {"cidr_block": "0.0.0.0/0", "gateway_id": igw.id}
    ],
    tags={"Name": f"{prefix}-rt"}
)

rt_assoc = aws.ec2.RouteTableAssociation(
    f"{prefix}-rt-assoc",
    subnet_id=subnet.id,
    route_table_id=route_table.id
)

# Create Security Group in the custom VPC
sg = aws.ec2.SecurityGroup(
    f"{prefix}-cluster-sg",
    vpc_id=vpc.id,
    description=f"Security group for {prefix} cluster",
    ingress=[
        # Allow all traffic within the SG
        {"protocol": "-1", "from_port": 0, "to_port": 0, "self": True},
        # Allow SSH from anywhere
        {"protocol": "tcp", "from_port": 22, "to_port": 22, "cidr_blocks": ["0.0.0.0/0"]},
    ],
    egress=[
        {"protocol": "-1", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"]},
    ],
)

# --- Key Pair setup ---
ssh_public_key_path = config.get('ssh_public_key_path')
with open(os.path.expanduser(ssh_public_key_path), 'r') as f:
    public_key = f.read().strip()
key_pair = aws.ec2.KeyPair(
    f"{prefix}-keypair",
    public_key=public_key,
)
pulumi.export("ec2_key_pair_name", key_pair.key_name)

# --- Prepare static IPs for each node ---
import ipaddress
subnet_base = ipaddress.ip_network(internal_subnet_cidr)
def ip_from_index(idx):
    # skip .0 (network) and .1 (gateway), start from .10 for familiarity
    return str(subnet_base.network_address + 10 + idx)
static_private_ips = [ip_from_index(i) for i in range(cluster_size)]

# --- Helper to render the cluster config XML for a node ---
def render_cluster_config(node_idx, all_ips, password):
    shards = []
    shards.append(f"""
        <shard>
            <replica>
                <host>localhost</host>
                <port>9000</port>
                <user>default</user>
                <password>{password}</password>
            </replica>
        </shard>""")
    for idx, ip in enumerate(all_ips):
        if idx == node_idx:
            continue
        shards.append(f"""
        <shard>
            <replica>
                <host>{ip}</host>
                <port>9000</port>
                <user>default</user>
                <password>{password}</password>
            </replica>
        </shard>""")
    return f"""<clickhouse>
<remote_servers>
    <default>
{''.join(shards)}
    </default>
</remote_servers>
</clickhouse>
"""

# --- Create EC2 instances with static private IPs and full user_data ---
instances = []
for i, name in enumerate(instance_names):
    node_ip = static_private_ips[i]
    node_config = render_cluster_config(i, static_private_ips, prefix)
    # Compose user_data: install ClickHouse, then write config
    base_script = get_user_data(dev_clickhouse_url)
    config_heredoc = node_config.replace('$', '\$')
    config_script = f"""
mkdir -p /etc/clickhouse-server/config.d
mkdir -p /etc/clickhouse-server/users.d
cat <<EOF > /etc/clickhouse-server/config.d/cluster.xml
{config_heredoc}
EOF
cat <<EOF > /etc/clickhouse-server/users.d/users.xml
<clickhouse>
    <users>
        <default>
            <password>{prefix}</password>
        </default>
    </users>
</clickhouse>
EOF
# Uncomment <listen_host>::</listen_host> in config.xml
sed -i 's/<!-- *<listen_host>::<\\/listen_host> *-->/<listen_host>::<\\/listen_host>/g' /etc/clickhouse-server/config.xml
systemctl enable clickhouse-server
systemctl restart clickhouse-server
"""
    full_user_data = base_script + config_script
    instance = aws.ec2.Instance(
        name,
        ami=ami_id,
        instance_type=instance_type,
        subnet_id=subnet.id,
        private_ip=node_ip,
        vpc_security_group_ids=[sg.id],
        key_name=key_pair.key_name,
        root_block_device={
            "volume_size": 500,
            "volume_type": "gp3",
            "delete_on_termination": True,
        },
        tags={"Name": name},
        user_data=full_user_data,
    )
    instances.append(instance)
