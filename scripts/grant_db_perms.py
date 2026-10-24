"""Grant schema permissions to incubrix user on both databases."""
import asyncio
import asyncpg


async def grant_permissions():
    for db in ["incubrix_dist", "incubrix_dist_test"]:
        conn = await asyncpg.connect(f"postgresql://postgres:postgres@localhost:5432/{db}")
        await conn.execute("GRANT ALL ON SCHEMA public TO incubrix")
        await conn.execute("GRANT CREATE ON SCHEMA public TO incubrix")
        await conn.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO incubrix")
        await conn.close()
        print(f"Granted permissions on {db}")

asyncio.run(grant_permissions())
