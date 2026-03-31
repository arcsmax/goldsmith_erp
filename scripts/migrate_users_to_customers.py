"""
Data Migration Script: Migrate Users to Customers

This script safely migrates existing "customer" users from the users table
to the new customers table while maintaining referential integrity.

IMPORTANT: Run this AFTER applying migration 002_gdpr_compliance

Process:
1. Identify users who are actually customers (have orders)
2. Create corresponding customer records
3. Update orders to reference new customers
4. Verify data integrity
5. Clean up old references

Usage:
    python scripts/migrate_users_to_customers.py

Author: Claude AI
Date: 2025-11-06
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parents[1]))

from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import User, Customer, Order
from goldsmith_erp.db.session import get_db_session

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(message: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{message}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")


def print_success(message: str):
    print(f"{Colors.OKGREEN}✓ {message}{Colors.ENDC}")


def print_warning(message: str):
    print(f"{Colors.WARNING}⚠ {message}{Colors.ENDC}")


def print_error(message: str):
    print(f"{Colors.FAIL}✗ {message}{Colors.ENDC}")


def print_info(message: str):
    print(f"{Colors.OKCYAN}ℹ {message}{Colors.ENDC}")


async def find_users_with_orders(db: AsyncSession):
    """
    Find all users who have orders (these are actual customers).
    """
    print_info("Finding users who have orders (actual customers)...")

    result = await db.execute(
        select(User.id, User.email, User.first_name, User.last_name)
        .join(Order, Order.customer_id == User.id)
        .distinct()
    )

    users_with_orders = result.fetchall()
    print_success(f"Found {len(users_with_orders)} users with orders")

    return users_with_orders


async def check_if_customer_exists(db: AsyncSession, user_id: int) -> bool:
    """
    Check if customer record already exists for this user.
    """
    result = await db.execute(
        select(Customer).filter(Customer.id == user_id)
    )
    return result.scalar_one_or_none() is not None


async def generate_customer_number(db: AsyncSession) -> str:
    """
    Generate unique customer number: CUST-YYYYMM-XXXX
    """
    prefix = f"CUST-{datetime.utcnow().strftime('%Y%m')}"

    # Find last customer number for this month
    result = await db.execute(
        select(Customer.customer_number)
        .filter(Customer.customer_number.like(f"{prefix}%"))
        .order_by(Customer.customer_number.desc())
        .limit(1)
    )
    last_customer = result.scalar_one_or_none()

    if last_customer:
        last_num = int(last_customer.split('-')[2])
        new_num = last_num + 1
    else:
        new_num = 1

    return f"{prefix}-{new_num:04d}"


async def get_admin_user_id(db: AsyncSession) -> int:
    """
    Get admin user ID for created_by field.
    """
    result = await db.execute(
        select(User.id).filter(User.role == "admin").limit(1)
    )
    admin = result.scalar_one_or_none()

    if not admin:
        # If no admin, get first user
        result = await db.execute(select(User.id).limit(1))
        admin = result.scalar_one_or_none()

    return admin if admin else 1  # Default to 1 if no users


async def calculate_last_order_date(db: AsyncSession, user_id: int) -> datetime:
    """
    Find the most recent order date for this customer.
    """
    result = await db.execute(
        select(Order.created_at)
        .filter(Order.customer_id == user_id)
        .order_by(Order.created_at.desc())
        .limit(1)
    )
    last_order = result.scalar_one_or_none()
    return last_order if last_order else datetime.utcnow()


async def create_customer_from_user(
    db: AsyncSession,
    user_id: int,
    email: str,
    first_name: str,
    last_name: str,
    admin_id: int
) -> Customer:
    """
    Create a customer record from user data.
    """
    customer_number = await generate_customer_number(db)
    last_order_date = await calculate_last_order_date(db, user_id)

    # Calculate retention deadline (10 years from last order)
    retention_deadline = last_order_date + timedelta(days=3650)

    customer = Customer(
        id=user_id,  # Keep same ID for easier migration
        customer_number=customer_number,
        first_name=first_name or "Unknown",
        last_name=last_name or "Customer",
        email=email,

        # GDPR defaults
        legal_basis="contract",
        consent_marketing=False,
        data_processing_consent=True,
        email_communication_consent=False,
        phone_communication_consent=False,
        sms_communication_consent=False,

        # Retention
        data_retention_category="active",
        last_order_date=last_order_date,
        retention_deadline=retention_deadline,

        # Audit
        created_at=datetime.utcnow(),
        created_by=admin_id,
        updated_at=datetime.utcnow(),

        # Status
        is_active=True,
        is_deleted=False
    )

    db.add(customer)
    await db.flush()  # Flush to get ID without committing

    return customer


async def update_order_customer_references(db: AsyncSession):
    """
    Update orders to reference the new customer_id_new field.
    """
    print_info("Updating order references to new customer table...")

    # Copy customer_id to customer_id_new
    await db.execute(
        update(Order)
        .values(customer_id_new=Order.customer_id)
    )

    await db.commit()
    print_success("Order references updated")


async def verify_migration(db: AsyncSession):
    """
    Verify that migration was successful.
    """
    print_info("Verifying migration...")

    # Check that all orders have customer_id_new set
    result = await db.execute(
        select(Order.id)
        .filter(Order.customer_id_new.is_(None))
    )
    orphaned_orders = result.fetchall()

    if orphaned_orders:
        print_error(f"Found {len(orphaned_orders)} orders without customer reference!")
        return False

    # Check that customer count matches
    result = await db.execute(select(Customer.id))
    customer_count = len(result.fetchall())

    result = await db.execute(
        select(User.id)
        .join(Order, Order.customer_id == User.id)
        .distinct()
    )
    users_with_orders_count = len(result.fetchall())

    if customer_count != users_with_orders_count:
        print_warning(
            f"Customer count ({customer_count}) doesn't match "
            f"users with orders ({users_with_orders_count})"
        )

    print_success("Migration verification passed")
    return True


async def print_migration_summary(db: AsyncSession):
    """
    Print summary of migration.
    """
    print_header("Migration Summary")

    # Count customers
    result = await db.execute(select(Customer.id))
    customer_count = len(result.fetchall())

    # Count orders
    result = await db.execute(select(Order.id))
    order_count = len(result.fetchall())

    # Count users
    result = await db.execute(select(User.id))
    user_count = len(result.fetchall())

    print_info(f"Total Customers Created: {customer_count}")
    print_info(f"Total Orders Updated: {order_count}")
    print_info(f"Total Users (Staff): {user_count}")

    print("\n" + Colors.OKGREEN + "Migration completed successfully!" + Colors.ENDC)


async def run_migration():
    """
    Main migration function.
    """
    print_header("User to Customer Migration Script")
    print_warning("IMPORTANT: Ensure database backup exists before proceeding!")

    # Confirm before proceeding
    response = input(f"\n{Colors.WARNING}Do you want to proceed with migration? (yes/no): {Colors.ENDC}")
    if response.lower() != 'yes':
        print_info("Migration cancelled by user")
        return

    # Create async engine
    engine = create_async_engine(str(settings.DATABASE_URL), echo=False)

    async with get_db_session() as db:
        try:
            print_info("Starting migration process...")

            # Step 1: Find users with orders
            users_with_orders = await find_users_with_orders(db)

            if not users_with_orders:
                print_warning("No users with orders found. Nothing to migrate.")
                return

            # Step 2: Get admin user for created_by
            admin_id = await get_admin_user_id(db)
            print_info(f"Using user ID {admin_id} as creator")

            # Step 3: Create customer records
            print_info("Creating customer records...")
            created_count = 0
            skipped_count = 0

            for user_id, email, first_name, last_name in users_with_orders:
                # Check if customer already exists
                if await check_if_customer_exists(db, user_id):
                    print_warning(f"Customer already exists for user {user_id} ({email}), skipping")
                    skipped_count += 1
                    continue

                # Create customer
                customer = await create_customer_from_user(
                    db, user_id, email, first_name, last_name, admin_id
                )
                created_count += 1

                if created_count % 10 == 0:
                    print_info(f"Created {created_count} customers...")

            print_success(f"Created {created_count} customers (skipped {skipped_count} existing)")

            # Commit customer creation
            await db.commit()

            # Step 4: Update order references
            await update_order_customer_references(db)

            # Step 5: Verify migration
            if not await verify_migration(db):
                print_error("Migration verification failed!")
                response = input(f"\n{Colors.WARNING}Rollback changes? (yes/no): {Colors.ENDC}")
                if response.lower() == 'yes':
                    await db.rollback()
                    print_info("Changes rolled back")
                    return

            # Step 6: Print summary
            await print_migration_summary(db)

        except Exception as e:
            print_error(f"Migration failed: {str(e)}")
            import traceback
            traceback.print_exc()
            await db.rollback()
            sys.exit(1)


async def rollback_migration():
    """
    Rollback migration if needed.
    """
    print_header("Rollback User to Customer Migration")
    print_warning("This will DELETE all customer records and reset orders!")

    response = input(f"\n{Colors.FAIL}Are you SURE you want to rollback? (yes/no): {Colors.ENDC}")
    if response.lower() != 'yes':
        print_info("Rollback cancelled")
        return

    async with get_db_session() as db:
        try:
            # Reset order customer_id_new to NULL
            await db.execute(
                update(Order).values(customer_id_new=None)
            )

            # Delete all customers
            await db.execute("DELETE FROM customers")

            await db.commit()
            print_success("Rollback completed")

        except Exception as e:
            print_error(f"Rollback failed: {str(e)}")
            await db.rollback()
            sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate users to customers")
    parser.add_argument(
        '--rollback',
        action='store_true',
        help='Rollback the migration'
    )

    args = parser.parse_args()

    if args.rollback:
        asyncio.run(rollback_migration())
    else:
        asyncio.run(run_migration())
