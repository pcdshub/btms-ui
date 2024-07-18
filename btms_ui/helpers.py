from __future__ import annotations

import ophyd
import pydm
from qtpy import QtCore


class PositionHelper(QtCore.QObject):
    """
    A helper for monitoring positions via PyDM channels.

    Emits ``position_updated`` whenever X or Y updates.

    Parameters
    ----------
    x : float, optional
        The starting X position.
    y : float, optional
        The starting Y position.
    channel_x : PyDMChannel, optional
        The PyDM channel for the X position.
    channel_y : PyDMChannel, optional
        The PyDM channel for the Y position.
    """

    #: Emitted on every X or Y update.
    position_updated = QtCore.Signal(object, object)  # Optional[float]
    #: Emitted on every X or Y update, including the offsets.
    position_set = QtCore.Signal(QtCore.QPointF)

    def __init__(
        self,
        x: float = 0.0,
        y: float = 0.0,
        channel_x: str | None = None,
        channel_y: str | None = None,
    ):
        super().__init__()
        self._channel_x = None
        self._channel_y = None
        self._channels = []
        self.channel_x = channel_x   # pyright: ignore
        self.channel_y = channel_y   # pyright: ignore
        self.x = x
        self.y = y

    def _remove_channel(self, channel: pydm.widgets.PyDMChannel):
        old_connections = [
            ch for ch in self._channels
            if ch.address == channel.address
        ]

        for channel in old_connections:
            channel.disconnect()
            self._channels.remove(channel)

    def _set_channel(
        self,
        old: pydm.widgets.PyDMChannel | None,
        new: str | None,
    ) -> pydm.widgets.PyDMChannel | None:
        """Update a channel setting."""
        if old is None and new is None:
            return None

        if old is not None:
            self._remove_channel(old)

        if not new:
            return None

        channel = pydm.widgets.PyDMChannel(address=new)
        self._channels.append(channel)
        return channel

    @QtCore.Property(str)
    def channel_x(self) -> str | None:   # pyright: ignore
        """The channel address for the X position."""
        if self._channel_x is None:
            return None
        return self._channel_x.address

    @channel_x.setter
    def channel_x(self, value: str | None):
        self._channel_x = self._set_channel(self._channel_x, value)
        if self._channel_x is None:
            return

        self._channel_x.value_slot = self._set_x
        self._channel_x.connect()

    @QtCore.Slot(int)
    @QtCore.Slot(float)
    def _set_x(self, value: float | int):
        self._update_position(float(value), None)

    @QtCore.Property(str)
    def channel_y(self) -> str | None:   # pyright: ignore
        """The channel address for the Y position."""
        if self._channel_y is None:
            return None
        return self._channel_y.address

    @channel_y.setter
    def channel_y(self, value: str | None):
        self._channel_y = self._set_channel(self._channel_y, value)
        if self._channel_y is None:
            return

        self._channel_y.value_slot = self._set_y
        self._channel_y.connect()

    @QtCore.Slot(int)
    @QtCore.Slot(float)
    def _set_y(self, value: float | int):
        self._update_position(None, float(value))

    def _update_position(self, x: float | None, y: float | None):
        """
        Hook for when X or Y position updated - signal to be emitted.

        Parameters
        ----------
        x : float, optional
            The new X position.
        y : float, optional
            The new Y position.
        """
        if x is not None:
            self.x = x
        if y is not None:
            self.y = y

        self.position_updated.emit(self.x, self.y)


class OphydCallbackHelper(QtCore.QObject):
    """
    A helper for monitoring an ophyd signal and emitting a signal.

    Emits ``updated`` whenever it gets an ophyd callback.

    Parameters
    ----------
    sig : ophyd.Signal
        The ophyd signal.
    event_type : str, optional
        The event type to subscribe to.
    """

    #: Emitted on every callback.
    updated = QtCore.Signal(dict)

    def __init__(
        self,
        sig: ophyd.Signal,
        event_type: str | None = None,
        subscribe_now: bool = False,
    ):
        super().__init__()
        self.sig = sig
        self.event_type = event_type
        self.cid = None
        if subscribe_now:
            self.subscribe()

    def subscribe(self, run: bool = True):
        """Start the subscription."""
        if self.cid is None:
            self.unsubscribe()
        self.cid = self.sig.subscribe(self._ophyd_callback, run=run)

    def unsubscribe(self):
        cid, self.cid = self.cid, None
        if cid is not None:
            self.sig.unsubscribe(cid)

    def _ophyd_callback(self, **kwargs):
        self.updated.emit(kwargs)


class AngleHelper(PositionHelper):
    """
    A lazy extension of PositionHelper.

    NOTE: If these are to be customized any further, these should be split up
    and implemented properly.
    """
    #: Emitted when the angle is updated from the control system.
    angle_updated = QtCore.Signal(float)
    #: Emitted when the final angle is set and applied to the group.
    angle_set = QtCore.Signal(float)

    def _update_position(self, angle: float | None, offset: float | None):
        """
        Hook for when X or Y position updated - signal to be emitted.

        Parameters
        ----------
        angle : float, optional
            The new angle.
        y : float, optional
            The new offset.
        """
        if angle is not None:
            self.x = angle
        if offset is not None:
            self.y = offset

        values = [value for value in (self.x, self.y) if value is not None]
        if values:
            self.angle = sum(values)
            self.angle_updated.emit(self.angle)
