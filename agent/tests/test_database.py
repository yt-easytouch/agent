from __future__ import annotations

import unittest
from shlex import quote

from testcontainers.mysql import MySqlContainer

from agent.database import Database


class DatabaseTestInstance:
    """Test database instance with few utility functions"""

    def __init__(self) -> None:
        self.db_root_password = "123456"
        self.db_container = MySqlContainer(image="mysql:8.0", MYSQL_ROOT_PASSWORD=self.db_root_password)
        self.db_container.start()

    @property
    def host(self):
        return self.db_container.get_container_host_ip()

    @property
    def port(self):
        return int(self.db_container.get_exposed_port(3306))

    def destroy(self) -> None:
        self.db_container.stop(force=True, delete_volume=True)

    def execute_cmd(self, cmd) -> str:
        code, output = self.db_container.exec(cmd)
        if code != 0:
            raise Exception(output.decode())
        return output.decode()

    def create_database(self, db_name: str):
        query = quote(f"CREATE DATABASE {db_name}")
        root_password = quote(self.db_root_password)
        self.execute_cmd(f"mysql -h 127.0.0.1 -uroot -p{root_password} -e {query}")

    def remove_database(self, db_name: str):
        query = quote(f"DROP DATABASE IF EXISTS {db_name}")
        root_password = quote(self.db_root_password)
        self.execute_cmd(f"mysql -h 127.0.0.1 -uroot -p{root_password} -e {query}")

    def create_database_user(self, db_name: str, username: str, password: str):
        queries = [
            f"CREATE USER '{username}'@'%' IDENTIFIED BY '{password}'",
            f"GRANT ALL ON {db_name}.* TO '{username}'@'%'",
            "FLUSH PRIVILEGES",
        ]
        for query in queries:
            command = f'mysql -h 127.0.0.1 -uroot -p{self.db_root_password} -e "{query}"'
            self.execute_cmd(command)

    def remove_database_user(self, username: str):
        query = quote(f"""
                      DROP USER IF EXISTS '{username}'@'%';
                      FLUSH PRIVILEGES;
                      """)
        root_password = quote(self.db_root_password)
        self.execute_cmd(f"mysql -h 127.0.0.1 -uroot -p{root_password} -e {query}")


class TestDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.instance = DatabaseTestInstance()

    @classmethod
    def tearDownClass(cls):
        cls.instance.destroy()

    def setUp(self) -> None:
        # create test databases (db1, db2) with user
        self.db1__name = "db1"
        self.db1__username = "db1_dummy_user1"
        self.db1__password = "db1_dummy_password"
        self._setup_db(self.db1__name, self.db1__username, self.db1__password)

        self.db2__name = "db2"
        self.db2__username = "db2_dummy_user1"
        self.db2__password = "db1_dummy_password"
        self._setup_db(self.db2__name, self.db2__username, self.db2__password)

    def _setup_db(self, db_name: str, username: str, password: str):
        # setup
        self.instance.create_database(db_name)
        self.instance.create_database_user(db_name, username, password)

        db = self._db(db_name, username, password)
        success, _ = db.execute_query(
            """
        CREATE TABLE Person (
            id int,
            name varchar(255)
        );
        INSERT INTO Person (id, name) VALUES (1, "John Doe");
        INSERT INTO Person (id, name) VALUES (2, "Jane Smith");
        INSERT INTO Person (id, name) VALUES (3, "Alice Johnson");
        INSERT INTO Person (id, name) VALUES (4, "Bob Brown");
        INSERT INTO Person (id, name) VALUES (5, "Charlie Davis");
        """,
            commit=True,
            as_dict=True,
        )
        if not success:
            raise Exception(f"Failed to prepare test database ({db_name})")

    def tearDown(self) -> None:
        self.instance.remove_database(self.db1__name)
        self.instance.remove_database_user(self.db1__username)

        self.instance.remove_database(self.db2__name)
        self.instance.remove_database_user(self.db2__username)

    def _db(self, db_name: str, username: str, password: str) -> Database:
        return Database(self.instance.host, self.instance.port, username, password, db_name)

    # Test cases for _run_sql method
    def test_run_sql_fn(self):
        """Basic test for `_run_sql` function"""
        db = self._db(self.db1__name, self.db1__username, self.db1__password)
        data = db._run_sql("SELECT * FROM Person", commit=False, as_dict=True)
        self.assertEqual(data[0]["row_count"], 5)

    def test_db1_user_shouldnt_be_able_to_access_db2(self):
        db = self._db(self.db2__name, self.db1__username, self.db1__password)
        with self.assertRaises(Exception) as cm:
            db._run_sql(
                """
                SELECT *
                FROM Person
                WHERE name = 'Bob Brown'
                """,
                commit=False,
                as_dict=True,
            )
        self.assertIn("Access denied for user 'db1_dummy_user1'@'%' to database 'db2'", str(cm.exception))

    def test_run_sql_fn_with_commit_disabled_shouldnt_allow_ddl_queries(self):
        db = self._db(self.db1__name, self.db1__username, self.db1__password)
        with self.assertRaises(Exception) as cm:
            db._run_sql(
                """
                CREATE TABLE Person2 (
                    id int,
                    name varchar(255)
                );
                """,
                commit=False,
                as_dict=True,
            )
        self.assertIn(
            "Provided DDL query is not allowed in read only mode",
            str(cm.exception),
            "DDL Query should be failed for non-commit mode",
        )

    def test_run_sql_fn_shouldnt_allow_dcl_queries(self):
        db = self._db(self.db1__name, self.db1__username, self.db1__password)
        with self.assertRaises(Exception) as cm:
            db._run_sql(
                """
                REVOKE ALL PRIVILEGES ON *.* FROM 'db1_dummy_user1'@'%';
                """,
                commit=True,
                as_dict=True,
            )
        self.assertIn(
            "DCL query is not allowed to execute",
            str(cm.exception),
            "DCL queries should be failed in any condition",
        )

    def test_run_sql_fn_shouldnt_allow_tcl_queries(self):
        db = self._db(self.db1__name, self.db1__username, self.db1__password)
        with self.assertRaises(Exception) as cm:
            db._run_sql(
                """
                COMMIT;
                """,
                commit=True,
                as_dict=True,
            )
        self.assertIn(
            "TCL query is not allowed to execute",
            str(cm.exception),
            "TCL queries should be failed in any condition",
        )

    def test_run_sql_fn_with_commit_enabled_should_persist_changes(self):
        db = self._db(self.db1__name, self.db1__username, self.db1__password)
        db._run_sql(
            """
            INSERT INTO Person (id, name) VALUES (6, "John Doe2");
            """,
            commit=True,
            as_dict=True,
        )
        data = db._run_sql(
            """
            SELECT *
            FROM Person
            WHERE name = 'John Doe2'
            """,
            commit=False,
            as_dict=True,
        )
        self.assertEqual(data[0]["row_count"], 1)

    def test_run_sql_fn_with_commit_disabled_should_not_persist_changes(self):
        db = self._db(self.db1__name, self.db1__username, self.db1__password)
        db._run_sql(
            """
            INSERT INTO Person (id, name) VALUES (6, "John Doe2");
            """,
            commit=False,
            as_dict=True,
        )
        data = db._run_sql(
            """
            SELECT *
            FROM Person
            WHERE name = 'John Doe2'
            """,
            commit=False,
            as_dict=True,
        )
        self.assertEqual(data[0]["row_count"], 0)
