#   Handles Firebase initialization and authentication
#   Provides a reusable initialize_firebase() function
#   Supports multiple authentication methods (service account JSON, environment variables, default credentials)
#   Includes proper error handling and logging


import firebase_admin
from firebase_admin import credentials, firestore
import logging
import os

logger = logging.getLogger(__name__)

def initialize_firebase(credentials_path=None):
    """Initialize Firebase app and return Firestore client.

    Args:
        credentials_path: Optional path to service account credentials JSON file.
                          If None, will use GOOGLE_APPLICATION_CREDENTIALS env var.

    Returns:
        firestore.Client: Initialized Firestore client

    Raises:
        Exception: If initialization fails
    """
    try:
        # Check if already initialized to avoid multiple initializations
        if not firebase_admin._apps:
            if credentials_path:
                cred = credentials.Certificate(credentials_path)
            else:
                # Check if env var is set first
                env_cred_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
                if env_cred_path and os.path.exists(env_cred_path):
                    logger.info(f"Using credentials from environment variable: {env_cred_path}")
                    cred = credentials.Certificate(env_cred_path)
                else:
                    # Fall back to application default credentials
                    logger.info("Using application default credentials")
                    cred = credentials.ApplicationDefault()

            firebase_admin.initialize_app(cred)
            logger.info("Firebase initialized successfully")
        else:
            logger.info("Using existing Firebase app instance")

        # Return Firestore client
        return firestore.client()

    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}", exc_info=True)
        raise