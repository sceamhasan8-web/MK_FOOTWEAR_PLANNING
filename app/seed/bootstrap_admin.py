"""
MK Footwear Planning - Initial Administrator Bootstrap Utility

Usage:
    python -m app.seed.bootstrap_admin [--reset-password]

Environment Variables:
    ERP_BOOTSTRAP_ADMIN_USERNAME (default: admin)
    ERP_BOOTSTRAP_ADMIN_PASSWORD (default: admin123 or specified strong password)
    ERP_BOOTSTRAP_ADMIN_EMAIL (default: admin@mkfootwear.com)
    ERP_BOOTSTRAP_ADMIN_NAME (default: MK Planning Administrator)
"""
import os
import sys
import logging
from app.database import SessionLocal, engine, Base
from app.models.user import User, UserRole
from app.api.deps import get_password_hash

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("erp.bootstrap_admin")


def bootstrap_administrator(force_reset_pwd: bool = False):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    username = os.getenv("ERP_BOOTSTRAP_ADMIN_USERNAME", "admin").strip()
    password = os.getenv("ERP_BOOTSTRAP_ADMIN_PASSWORD", "admin123")
    email = os.getenv("ERP_BOOTSTRAP_ADMIN_EMAIL", "admin@mkfootwear.com").strip()
    full_name = os.getenv("ERP_BOOTSTRAP_ADMIN_NAME", "MK Planning Administrator").strip()

    if not username:
        logger.error("Bootstrap aborted: Username cannot be blank.")
        sys.exit(1)

    if len(password) < 6:
        logger.error("Bootstrap aborted: Password must be at least 6 characters.")
        sys.exit(1)

    try:
        existing_admin = db.query(User).filter(User.username == username).first()
        if existing_admin:
            if force_reset_pwd:
                existing_admin.hashed_password = get_password_hash(password)
                existing_admin.role = UserRole.ADMIN
                existing_admin.is_active = True
                db.commit()
                logger.info("Administrator '%s' password reset successfully via bootstrap.", username)
            else:
                logger.info("Administrator '%s' already exists with active status. Password untouched.", username)
                # Ensure it has ADMIN role
                if existing_admin.role != UserRole.ADMIN:
                    existing_admin.role = UserRole.ADMIN
                    db.commit()
                    logger.info("Ensured Administrator role on user '%s'.", username)
            return existing_admin

        # Create fresh admin
        new_admin = User(
            username=username,
            email=email,
            full_name=full_name,
            role=UserRole.ADMIN,
            hashed_password=get_password_hash(password),
            is_active=True,
        )
        db.add(new_admin)
        db.commit()
        db.refresh(new_admin)
        logger.info("Initial Administrator '%s' created successfully (ID: %s).", username, new_admin.id)
        return new_admin
    finally:
        db.close()


if __name__ == "__main__":
    force_reset = "--reset-password" in sys.argv
    bootstrap_administrator(force_reset_pwd=force_reset)
