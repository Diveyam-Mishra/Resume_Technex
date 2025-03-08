"""
Error message constants to be used across the application.
"""
from enum import Enum


class ErrorMessage(str, Enum):
    # Auth related errors
    INVALID_CREDENTIALS = "The email or password you entered is incorrect."
    INVALID_REFRESH_TOKEN = "The refresh token is invalid or expired."
    INVALID_RESET_TOKEN = "The password reset token is invalid or expired."
    INVALID_VERIFICATION_TOKEN = "The email verification token is invalid or expired."
    INVALID_TWO_FACTOR_CODE = "The two-factor authentication code is invalid."
    INVALID_TWO_FACTOR_BACKUP_CODE = "The two-factor backup code is invalid."
    OAUTH_USER = "This account was created using a third-party provider. Please sign in using that provider."
    EMAIL_ALREADY_VERIFIED = "Your email has already been verified."
    TWO_FACTOR_ALREADY_ENABLED = "Two-factor authentication is already enabled on your account."
    TWO_FACTOR_NOT_ENABLED = "Two-factor authentication is not enabled on your account."
    
    # User related errors
    USER_ALREADY_EXISTS = "A user with this email or username already exists."
    USER_NOT_FOUND = "The user with the specified ID was not found."
    SECRETS_NOT_FOUND = "The user's secrets were not found."
    
    # Resume related errors
    RESUME_NOT_FOUND = "The resume with the specified ID was not found."
    RESUME_SLUG_ALREADY_EXISTS = "A resume with this slug already exists."
    RESUME_LOCKED = "This resume is currently locked and cannot be edited."
    RESUME_PRINTER_ERROR = "An error occurred while generating the resume PDF."
    
    # Infrastructure related errors
    INVALID_BROWSER_CONNECTION = "Could not connect to the browser for PDF generation."
    SOMETHING_WENT_WRONG = "Something went wrong. Please try again later."