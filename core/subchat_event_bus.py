# /core/subchat_event_bus.py

import threading
from typing import Callable, Dict, List, Any


class SubChatEventBus:
    """
    Lightweight internal event bus for SubChat system.
    Handles subscription, unsubscription, and event dispatch.
    Used by routers, controllers, storage, and monitors.
    """

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_name: str, callback: Callable):
        """
        Register a callback for a given event.
        """
        with self._lock:
            if event_name not in self._subscribers:
                self._subscribers[event_name] = []
            if callback not in self._subscribers[event_name]:
                self._subscribers[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callable):
        """
        Remove callback from an event subscription.
        """
        with self._lock:
            if event_name in self._subscribers:
                if callback in self._subscribers[event_name]:
                    self._subscribers[event_name].remove(callback)

    def emit(self, event_name: str, payload: Any = None):
        """
        Send an event with optional data.
        Each callback is executed sequentially.
        """
        with self._lock:
            callbacks = list(self._subscribers.get(event_name, []))

        for callback in callbacks:
            try:
                callback(payload)
            except Exception as e:
                print(f"[SubChatEventBus] Error in event '{event_name}' handler: {e}")

    def clear_all(self):
        """
        Remove all subscribers (used in shutdown or sandbox mode reset).
        """
        with self._lock:
            self._subscribers.clear()


# Singleton instance for global use
subchat_event_bus = SubChatEventBus()