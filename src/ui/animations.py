"""Small reusable Pygame animations for the Griductive board UI."""

from __future__ import annotations

import pygame


class CardFlipAnimation:
    """Horizontal card flip used when a proved card reveals its clue.

    Call :meth:`update` once per frame and use :meth:`frame` to get the card
    rectangle and whether the front face should be drawn. A duration of 0.34s
    matches the reference GUI's reveal timing.
    """

    def __init__(self, duration: float = 0.34) -> None:
        if duration <= 0:
            raise ValueError("Animation duration must be positive.")
        self.duration = duration
        self.elapsed = 0.0

    @property
    def progress(self) -> float:
        return min(1.0, self.elapsed / self.duration)

    @property
    def finished(self) -> bool:
        return self.elapsed >= self.duration

    def update(self, dt: float) -> bool:
        """Advance by ``dt`` seconds; return True once the flip is complete."""
        self.elapsed = min(self.duration, self.elapsed + max(0.0, dt))
        return self.finished

    def frame(self, rect: pygame.Rect) -> tuple[pygame.Rect, bool]:
        """Return the horizontally squeezed rect and face to render this frame."""
        progress = self.progress
        draw_rect = rect.copy()
        width_scale = max(0.04, abs(1.0 - 2.0 * progress))
        draw_rect.width = max(4, int(rect.width * width_scale))
        draw_rect.centerx = rect.centerx
        return draw_rect, progress >= 0.5
