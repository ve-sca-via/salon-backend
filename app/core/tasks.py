"""
Background tasks and lifespan management for FastAPI application.
Handles graceful startup and shutdown with background task orchestration.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import get_db

logger = logging.getLogger(__name__)


async def cleanup_expired_tokens_task(shutdown_event: asyncio.Event):
    """
    Background task to cleanup expired tokens periodically with graceful shutdown.
    Runs indefinitely until shutdown_event is set.
    """
    from app.core.auth import cleanup_expired_tokens
    
    db = get_db()
    
    while not shutdown_event.is_set():
        try:
            logger.info("Running scheduled token cleanup...")
            cleaned_count = cleanup_expired_tokens(db)
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} expired tokens")
            else:
                logger.debug("No expired tokens to clean up")
        except Exception as e:
            logger.error(f"Token cleanup task error: {str(e)}", exc_info=True)
        
        # Run every N seconds, but allow graceful shutdown
        try:
            await asyncio.wait_for(
                shutdown_event.wait(),
                timeout=settings.TOKEN_CLEANUP_INTERVAL_SECONDS
            )
            # If we reach here, shutdown was signaled
            break
        except asyncio.TimeoutError:
            # Timeout means continue the loop (interval passed)
            pass
    
    logger.info("Cleanup task shutdown gracefully")


@asynccontextmanager
async def lifespan(app):
    """
    Application lifespan event handler for startup and shutdown tasks.
    Manages background task creation and graceful shutdown.
    """
    # Create shutdown event for graceful task termination
    shutdown_event = asyncio.Event()
    
    # Startup: Start background tasks
    logger.info("Starting background tasks")
    cleanup_task = asyncio.create_task(cleanup_expired_tokens_task(shutdown_event))
    logger.info("Background tasks started")
    
    yield
    
    # Shutdown: Signal tasks to stop gracefully
    logger.info("Shutting down background tasks...")
    shutdown_event.set()  # Signal the task to stop
    
    try:
        # Wait for task to finish gracefully (with timeout)
        await asyncio.wait_for(
            cleanup_task,
            timeout=settings.BACKGROUND_SHUTDOWN_TIMEOUT_SECONDS
        )
        logger.info("All background tasks stopped gracefully")
    except asyncio.TimeoutError:
        logger.warning("Cleanup task didn't stop in time, forcing cancellation")
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            logger.info("Cleanup task force-cancelled")
    except Exception as e:
        logger.error(f"Error during task shutdown: {e}", exc_info=True)
