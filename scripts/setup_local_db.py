"""Setup local PostgreSQL databases for development and testing."""
import asyncio
import asyncpg


async def setup():
    conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/postgres")

    # Create user if not exists
    existing = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname='incubrix'")
    if not existing:
        await conn.execute("CREATE USER incubrix WITH PASSWORD 'incubrix_dev_password'")
        print("Created user incubrix")
    else:
        await conn.execute("ALTER USER incubrix WITH PASSWORD 'incubrix_dev_password'")
        print("Updated password for user incubrix")

    # Create databases
    for db in ["incubrix_dist", "incubrix_dist_test"]:
        existing_db = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname=$1", db
        )
        if not existing_db:
            await conn.execute(f"CREATE DATABASE {db} OWNER incubrix")
            print(f"Created database {db}")
        else:
            print(f"Database {db} already exists")

    await conn.close()
    print("DB setup complete.")


asyncio.run(setup())
