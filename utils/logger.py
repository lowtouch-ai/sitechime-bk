"""
Logger utility for the cloudcontrol_widget_backend project.
"""
import logging

# Get pre-configured loggers
django_logger = logging.getLogger('django')
api_logger = logging.getLogger('api')
security_logger = logging.getLogger('django.security')
db_logger = logging.getLogger('django.db.backends')


def get_logger(name):
    """
    Get a logger for the specified module.
    
    Args:
        name (str): Name of the module (typically __name__)
    
    Returns:
        logging.Logger: Configured logger for the module
    """
    return logging.getLogger(name)


# Example usage:
# from utils.logger import api_logger, security_logger, db_logger
# 
# api_logger.debug("Debug message")
# api_logger.info("Info message")
# api_logger.warning("Warning message")
# api_logger.error("Error message")
# api_logger.critical("Critical message")
# 
# # For security-related events:
# security_logger.info("User login attempt")
# security_logger.warning("Multiple failed login attempts")
# 
# # For database operations (only logged when DEBUG=True):
# db_logger.debug("Database query information")