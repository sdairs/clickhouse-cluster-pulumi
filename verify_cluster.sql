CREATE TABLE test ENGINE = MergeTree() ORDER BY b AS SELECT * FROM generateRandom('a UUID,b DateTime,c Text') LIMIT 1000;
SELECT count() FROM test;
CREATE TABLE test_d as test ENGINE = Distributed(default, default, test, rand());
SELECT count() FROM test_d;