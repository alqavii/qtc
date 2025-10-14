"""
API server lifecycle management.

Handles startup validation, shutdown coordination, and SSE connection tracking
for graceful server lifecycle events.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Set


class ServerLifecycle:
    """Manages API server lifecycle state and coordination."""
    
    def __init__(self):
        self._active_sse_queues: Set[asyncio.Queue] = set()
        self._is_shutting_down = False
        self._startup_complete = False
    
    @property
    def is_shutting_down(self) -> bool:
        """Check if server is currently shutting down."""
        return self._is_shutting_down
    
    @property
    def is_ready(self) -> bool:
        """Check if server startup is complete."""
        return self._startup_complete
    
    def track_sse_connection(self, queue: asyncio.Queue) -> None:
        """Register an active SSE connection for tracking.
        
        Args:
            queue: The asyncio queue used for this SSE connection
        """
        self._active_sse_queues.add(queue)
    
    def untrack_sse_connection(self, queue: asyncio.Queue) -> None:
        """Remove an SSE connection from tracking.
        
        Args:
            queue: The asyncio queue to remove
        """
        self._active_sse_queues.discard(queue)
    
    def get_active_sse_count(self) -> int:
        """Get count of active SSE connections."""
        return len(self._active_sse_queues)
    
    async def startup(self, data_root: Path) -> None:
        """Execute startup validation and initialization.
        
        Args:
            data_root: Path to the data directory to validate
        """
        # Validate data directory and check disk space if available
        if data_root.exists():
            try:
                disk_usage = shutil.disk_usage(data_root)
                free_gb = disk_usage.free / (1024 ** 3)
                # Silent validation - warnings handled by health check endpoint
            except Exception:
                pass
        
        self._startup_complete = True
    
    async def shutdown(self, timeout: float = 5.0) -> None:
        """Execute graceful shutdown sequence.
        
        Args:
            timeout: Maximum time to wait for SSE connections to close (seconds)
        """
        self._is_shutting_down = True
        
        # Close all active SSE connections
        connection_count = len(self._active_sse_queues)
        if connection_count > 0:
            # Send shutdown signal to all connections
            for queue in list(self._active_sse_queues):
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    # Queue is full, connection should drain and close anyway
                    pass
                except Exception:
                    # Silent error handling - connection will be cleaned up
                    pass
            
            # Wait for connections to close gracefully
            wait_time = min(timeout, 5.0)  # Cap at 5 seconds
            try:
                await asyncio.wait_for(
                    self._wait_for_sse_close(),
                    timeout=wait_time
                )
            except asyncio.TimeoutError:
                # Timeout reached, proceed with shutdown anyway
                pass
    
    async def _wait_for_sse_close(self) -> None:
        """Wait for all SSE connections to close."""
        while len(self._active_sse_queues) > 0:
            await asyncio.sleep(0.1)


# Global lifecycle manager instance
lifecycle = ServerLifecycle()
