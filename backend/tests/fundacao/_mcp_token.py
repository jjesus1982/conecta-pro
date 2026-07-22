"""Token JWT real p/ testes standalone (sem pytest). Espelha _make_real_token do conftest,
mas sem pytest.skip — levanta RuntimeError se o ambiente não tiver os segredos.
jjesus@conectamais.pro está na allowlist da diretoria → passa no require_mcp_consultor."""
import os, datetime
import jwt as pyjwt
from sqlalchemy import create_engine, text


def make_token() -> str:
    secret = os.environ["JWT_SECRET_KEY"]                       # presente no container
    algo = os.environ.get("JWT_ALGORITHM", "HS256")
    db_url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    engine = create_engine(db_url)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT id, email FROM users WHERE email='jjesus@conectamais.pro' LIMIT 1")).fetchone()
    engine.dispose()
    if not row:
        raise RuntimeError("user jjesus@conectamais.pro não encontrado")
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {"sub": str(row[0]), "email": row[1], "type": "access",
               "role": "admin", "exp": now + datetime.timedelta(hours=2)}
    return pyjwt.encode(payload, secret, algorithm=algo)
