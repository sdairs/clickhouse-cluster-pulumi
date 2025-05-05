# AWS ClickHouse Cluster Pulumi Template

A minimal Pulumi template for provisioning a basic ClickHouse cluster on AWS for testing and development purposes.

## Overview

This template provisions a simple ClickHouse cluster on AWS EC2 instances, with automated networking and configuration. It is designed for rapid testing, experimentation, and learning. The cluster is not production-hardened, but provides a solid foundation for further customization.

**Features:**
- Creates a custom VPC and subnet (configurable CIDRs)
- Launches multiple EC2 instances (cluster size configurable)
- Assigns static private IPs to each node for predictable cluster config
- Attaches a 500GB gp3 EBS root volume to each instance
- Provisions SSH access via a user-supplied SSH public key
- Installs ClickHouse and generates cluster configuration via user data
- Sets the default ClickHouse user password to the cluster prefix
- Exposes all nodes to the internet for SSH (for testing)

## Prerequisites

- AWS account with permissions to create VPCs, EC2 instances, and related resources (see [automation-iam-policy.json](automation-iam-policy.json))
- AWS credentials configured in your environment
- SSH key pair created with public key available locally
- Python 3.12 or later
- Pulumi CLI installed and logged in (use `pulumi login --local`)
- `uv` installed

## Creating a cluster

1. Clone this repository
2. Configure your stack (see `Pulumi.dev.yaml` for example):
   - Set AWS region, cluster size, instance type, prefix, and SSH public key path
   - (optionally) custom VPC/subnet CIDRs
   - (optionally) custom ClickHouse build URL
3. Preview the infrastructure:
```bash
pulumi preview
```
4. Deploy the cluster:
```bash
pulumi up
```

## Destroying a cluster

1. Tear down the cluster:
```bash
pulumi destroy
```

## Configuration Options

- `clickhouse-cluster:prefix`: Resource naming prefix and ClickHouse default password
- `clickhouse-cluster:cluster_size`: Number of ClickHouse nodes to launch
- `clickhouse-cluster:instance_type`: EC2 instance type
- `clickhouse-cluster:ssh_public_key_path`: Path to your SSH public key
- `clickhouse-cluster:internal_vpc_cidr`: VPC CIDR block (default: 10.10.0.0/16)
- `clickhouse-cluster:internal_subnet_cidr`: Subnet CIDR block (default: 10.10.0.0/24)
- `clickhouse-cluster:dev_clickhouse_url`: Custom ClickHouse build URL (optional)

## What’s Created
- Custom VPC, subnet, route table, and IGW for public access
- Security group for SSH and intra-cluster traffic
- EC2 instances with static private IPs and 500GB gp3 EBS volumes
- ClickHouse installed and configured on each node
- User data sets up cluster config and user password automatically

## Notes
- This template is for testing and development only. For production, restrict SSH, secure credentials, and review security group rules.
- The default ClickHouse password is set to the `prefix` value.
- All configuration is performed at instance boot—no manual SSH or post-provisioning needed.