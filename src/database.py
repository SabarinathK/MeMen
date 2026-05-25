from sqlmodel import SQLModel, create_engine, Session
from src.models import User
from passlib.context import CryptContext
from src.config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(password: str) -> str:
    password = password[:72]
    return pwd_context.hash(password)


def create_db():
    SQLModel.metadata.create_all(engine)


def get_session():
    return Session(engine)


def create_sample_user():
    with Session(engine) as session:

        user = User(
            username="sabari",
            email="user1@example.com",
            hashed_password=hash_password("sabari"),
            memory_consent=True,
        )

        session.add(user)
        session.commit()
        session.refresh(user)


if __name__ == "__main__":
    create_db()
    # create_sample_user()
