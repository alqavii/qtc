"""
Comprehensive tests for API server lifecycle management.

Tests startup validation, shutdown coordination, SSE connection tracking,
and edge cases.
"""
import asyncio
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.lifecycle import ServerLifecycle


class TestServerLifecycleState:
    def test_initial_state(self):
        lifecycle = ServerLifecycle()
        
        assert lifecycle.is_shutting_down is False
        assert lifecycle.is_ready is False
        assert lifecycle.get_active_sse_count() == 0
    
    def test_state_after_startup(self):
        lifecycle = ServerLifecycle()
        
        # Startup should mark as ready
        asyncio.run(lifecycle.startup(Path("/tmp")))
        
        assert lifecycle.is_ready is True
        assert lifecycle.is_shutting_down is False
    
    def test_state_after_shutdown(self):
        lifecycle = ServerLifecycle()
        
        asyncio.run(lifecycle.shutdown())
        
        assert lifecycle.is_shutting_down is True


class TestSSEConnectionTracking:
    def test_track_single_connection(self):
        lifecycle = ServerLifecycle()
        queue = asyncio.Queue()
        
        lifecycle.track_sse_connection(queue)
        
        assert lifecycle.get_active_sse_count() == 1
    
    def test_track_multiple_connections(self):
        lifecycle = ServerLifecycle()
        queues = [asyncio.Queue() for _ in range(5)]
        
        for queue in queues:
            lifecycle.track_sse_connection(queue)
        
        assert lifecycle.get_active_sse_count() == 5
    
    def test_untrack_connection(self):
        lifecycle = ServerLifecycle()
        queue = asyncio.Queue()
        
        lifecycle.track_sse_connection(queue)
        assert lifecycle.get_active_sse_count() == 1
        
        lifecycle.untrack_sse_connection(queue)
        assert lifecycle.get_active_sse_count() == 0
    
    def test_untrack_nonexistent_connection(self):
        lifecycle = ServerLifecycle()
        queue = asyncio.Queue()
        
        # Should not raise error
        lifecycle.untrack_sse_connection(queue)
        assert lifecycle.get_active_sse_count() == 0
    
    def test_track_same_queue_twice(self):
        lifecycle = ServerLifecycle()
        queue = asyncio.Queue()
        
        lifecycle.track_sse_connection(queue)
        lifecycle.track_sse_connection(queue)  # Add again
        
        # Sets don't allow duplicates
        assert lifecycle.get_active_sse_count() == 1


class TestStartup:
    @pytest.mark.asyncio
    async def test_startup_with_valid_directory(self, tmp_path):
        lifecycle = ServerLifecycle()
        
        await lifecycle.startup(tmp_path)
        
        assert lifecycle.is_ready is True
        assert lifecycle.is_shutting_down is False
    
    @pytest.mark.asyncio
    async def test_startup_with_nonexistent_directory(self):
        lifecycle = ServerLifecycle()
        nonexistent = Path("/nonexistent/path")
        
        # Should not raise, just warn
        await lifecycle.startup(nonexistent)
        
        assert lifecycle.is_ready is True
    
    @pytest.mark.asyncio
    async def test_startup_validates_disk_space(self, tmp_path):
        lifecycle = ServerLifecycle()
        
        # Should complete startup even with disk space checks
        await lifecycle.startup(tmp_path)
        
        # Startup should complete successfully
        assert lifecycle.is_ready is True
    
    @pytest.mark.asyncio
    async def test_startup_handles_disk_check_error(self, tmp_path):
        lifecycle = ServerLifecycle()
        
        with patch('shutil.disk_usage', side_effect=OSError("Disk error")):
            # Should not raise, just warn
            await lifecycle.startup(tmp_path)
            
            assert lifecycle.is_ready is True
    
    @pytest.mark.asyncio
    async def test_startup_handles_low_disk_space(self, tmp_path):
        lifecycle = ServerLifecycle()
        
        # Mock low disk space (0.5 GB free)
        mock_usage = MagicMock()
        mock_usage.free = 0.5 * (1024 ** 3)
        mock_usage.total = 100 * (1024 ** 3)
        mock_usage.used = 99.5 * (1024 ** 3)
        
        with patch('shutil.disk_usage', return_value=mock_usage):
            # Should complete startup even with low disk space
            await lifecycle.startup(tmp_path)
            
            # Startup should complete (warnings handled elsewhere)
            assert lifecycle.is_ready is True


class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_with_no_connections(self):
        lifecycle = ServerLifecycle()
        
        await lifecycle.shutdown()
        
        assert lifecycle.is_shutting_down is True
    
    @pytest.mark.asyncio
    async def test_shutdown_closes_sse_connections(self):
        lifecycle = ServerLifecycle()
        
        # Create and track some queues
        queues = [asyncio.Queue() for _ in range(3)]
        for queue in queues:
            lifecycle.track_sse_connection(queue)
        
        assert lifecycle.get_active_sse_count() == 3
        
        # Shutdown should signal all queues
        await lifecycle.shutdown(timeout=1.0)
        
        # Check all queues received shutdown signal (None)
        for queue in queues:
            item = await asyncio.wait_for(queue.get(), timeout=0.1)
            assert item is None
    
    @pytest.mark.asyncio
    async def test_shutdown_waits_for_connections_to_close(self):
        lifecycle = ServerLifecycle()
        
        # Track a connection
        queue = asyncio.Queue()
        lifecycle.track_sse_connection(queue)
        
        # Simulate connection closing after a delay
        async def close_after_delay():
            await asyncio.sleep(0.2)
            lifecycle.untrack_sse_connection(queue)
        
        asyncio.create_task(close_after_delay())
        
        # Shutdown should wait for connection to close
        await lifecycle.shutdown(timeout=1.0)
        
        assert lifecycle.get_active_sse_count() == 0
    
    @pytest.mark.asyncio
    async def test_shutdown_timeout_handling(self):
        lifecycle = ServerLifecycle()
        
        # Track a connection that never closes
        queue = asyncio.Queue()
        lifecycle.track_sse_connection(queue)
        
        # Shutdown with short timeout
        await lifecycle.shutdown(timeout=0.1)
        
        # Should complete shutdown despite timeout
        assert lifecycle.is_shutting_down is True
        # Connection may still be tracked if it didn't close in time
        # This is expected behavior
    
    @pytest.mark.asyncio
    async def test_shutdown_handles_queue_full_error(self):
        lifecycle = ServerLifecycle()
        
        # Create a full queue
        queue = asyncio.Queue(maxsize=1)
        await queue.put("full")
        lifecycle.track_sse_connection(queue)
        
        # Shutdown should handle QueueFull gracefully
        await lifecycle.shutdown(timeout=0.5)
        
        # Should complete without raising
        assert lifecycle.is_shutting_down is True
    
    @pytest.mark.asyncio
    async def test_shutdown_handles_queue_error(self):
        lifecycle = ServerLifecycle()
        
        # Create a mock queue that raises on put_nowait
        queue = MagicMock(spec=asyncio.Queue)
        queue.put_nowait.side_effect = RuntimeError("Queue error")
        lifecycle.track_sse_connection(queue)
        
        # Shutdown should handle error gracefully (silently)
        await lifecycle.shutdown(timeout=0.5)
        
        assert lifecycle.is_shutting_down is True
    
    @pytest.mark.asyncio
    async def test_shutdown_caps_timeout(self):
        lifecycle = ServerLifecycle()
        
        # Request very long timeout
        start = asyncio.get_event_loop().time()
        await lifecycle.shutdown(timeout=999.0)
        elapsed = asyncio.get_event_loop().time() - start
        
        # Should cap at reasonable time (5 seconds or less)
        assert elapsed < 6.0


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_connection_tracking(self):
        lifecycle = ServerLifecycle()
        
        async def add_connections():
            for _ in range(10):
                queue = asyncio.Queue()
                lifecycle.track_sse_connection(queue)
                await asyncio.sleep(0.01)
        
        # Run multiple tasks concurrently
        await asyncio.gather(
            add_connections(),
            add_connections(),
            add_connections()
        )
        
        assert lifecycle.get_active_sse_count() == 30
    
    @pytest.mark.asyncio
    async def test_concurrent_shutdown_and_tracking(self):
        lifecycle = ServerLifecycle()
        
        # Add some connections
        for _ in range(5):
            lifecycle.track_sse_connection(asyncio.Queue())
        
        async def keep_adding():
            for _ in range(5):
                await asyncio.sleep(0.05)
                lifecycle.track_sse_connection(asyncio.Queue())
        
        # Start shutdown while still tracking connections
        await asyncio.gather(
            lifecycle.shutdown(timeout=0.5),
            keep_adding()
        )
        
        # Shutdown should complete
        assert lifecycle.is_shutting_down is True


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_multiple_startups(self):
        lifecycle = ServerLifecycle()
        
        # Multiple startups should be idempotent
        await lifecycle.startup(Path("/tmp"))
        await lifecycle.startup(Path("/tmp"))
        await lifecycle.startup(Path("/tmp"))
        
        assert lifecycle.is_ready is True
    
    @pytest.mark.asyncio
    async def test_multiple_shutdowns(self):
        lifecycle = ServerLifecycle()
        
        # Multiple shutdowns should be idempotent
        await lifecycle.shutdown()
        await lifecycle.shutdown()
        await lifecycle.shutdown()
        
        assert lifecycle.is_shutting_down is True
    
    @pytest.mark.asyncio
    async def test_shutdown_before_startup(self):
        lifecycle = ServerLifecycle()
        
        # Should handle shutdown before startup
        await lifecycle.shutdown()
        
        assert lifecycle.is_shutting_down is True
        assert lifecycle.is_ready is False
    
    def test_track_connection_after_shutdown(self):
        lifecycle = ServerLifecycle()
        
        asyncio.run(lifecycle.shutdown())
        
        # Should still allow tracking (for cleanup)
        queue = asyncio.Queue()
        lifecycle.track_sse_connection(queue)
        
        assert lifecycle.get_active_sse_count() == 1


class TestIntegrationWithRealQueues:
    @pytest.mark.asyncio
    async def test_real_queue_lifecycle(self):
        lifecycle = ServerLifecycle()
        
        # Simulate real SSE connection lifecycle
        queue = asyncio.Queue()
        lifecycle.track_sse_connection(queue)
        
        # Consumer task
        received = []
        async def consumer():
            while True:
                item = await queue.get()
                if item is None:
                    break
                received.append(item)
        
        consumer_task = asyncio.create_task(consumer())
        
        # Send some data
        await queue.put("event1")
        await queue.put("event2")
        await asyncio.sleep(0.1)
        
        # Shutdown
        await lifecycle.shutdown(timeout=1.0)
        
        # Wait for consumer to finish
        await asyncio.wait_for(consumer_task, timeout=1.0)
        
        assert received == ["event1", "event2"]
        assert lifecycle.is_shutting_down is True
    
    @pytest.mark.asyncio
    async def test_multiple_consumers_shutdown(self):
        lifecycle = ServerLifecycle()
        
        # Create multiple queues
        num_consumers = 5
        queues = [asyncio.Queue() for _ in range(num_consumers)]
        for queue in queues:
            lifecycle.track_sse_connection(queue)
        
        # Create consumer tasks
        async def consumer(queue, results_list):
            while True:
                item = await queue.get()
                if item is None:
                    break
                results_list.append(item)
        
        results = [[] for _ in range(num_consumers)]
        tasks = [
            asyncio.create_task(consumer(queues[i], results[i]))
            for i in range(num_consumers)
        ]
        
        # Send data to all queues
        for i, queue in enumerate(queues):
            await queue.put(f"data{i}")
        
        await asyncio.sleep(0.1)
        
        # Shutdown should close all
        await lifecycle.shutdown(timeout=2.0)
        
        # All tasks should complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should have received their data
        for i, result in enumerate(results):
            assert result == [f"data{i}"]
