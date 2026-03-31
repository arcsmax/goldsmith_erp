"""Factory for User model test data."""
import factory
from goldsmith_erp.db.models import User, UserRole


# Pre-computed bcrypt hash for "TestPass123!" to avoid passlib/bcrypt
# compatibility issues and speed up factory builds.
# To regenerate: python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('TestPass123!'))"
_TEST_PASSWORD_HASH = "$2b$12$LJ3m4ys3Lg2RqFWiYMJdse4OMaSsIuMbkCBiMXGMOiVYNpS5oUaQm"


class UserFactory(factory.Factory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@goldsmith-test.de")
    first_name = factory.Faker("first_name", locale="de_DE")
    last_name = factory.Faker("last_name", locale="de_DE")
    hashed_password = _TEST_PASSWORD_HASH
    role = UserRole.GOLDSMITH
    is_active = True


class AdminFactory(UserFactory):
    email = factory.Sequence(lambda n: f"admin{n}@goldsmith-test.de")
    role = UserRole.ADMIN


class ViewerFactory(UserFactory):
    email = factory.Sequence(lambda n: f"viewer{n}@goldsmith-test.de")
    role = UserRole.VIEWER
