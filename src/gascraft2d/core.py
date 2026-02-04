from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, TypedDict, cast

import pygame

# --- Core constants ---------------------------------------------------------
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60
TILE_SIZE = 32
CHUNK_SIZE = 16
WORLD_HEIGHT = 180
SAVE_PATH = Path("gascraft2d_save.json")

# Palette
BG_DARK = (5, 10, 20)
NEON_CYAN = (0, 255, 255)
NEON_MAGENTA = (255, 0, 255)
NEON_YELLOW = (255, 255, 0)
NEON_GREEN = (0, 255, 100)
NEON_ORANGE = (255, 128, 0)
NEON_RED = (255, 50, 50)
NEON_BLUE = (90, 140, 255)


@dataclass(frozen=True)
class BlockDef:
    id: int
    name: str
    color: Tuple[int, int, int]
    glow: Tuple[int, int, int]
    break_time: float
    solid: bool
    placeable: bool = True
    unbreakable: bool = False
    drop_id: Optional[int] = None


BLOCK_AIR = 0
BLOCK_DIRT = 1
BLOCK_STONE = 2
BLOCK_ORE = 3
BLOCK_WOOD = 4
BLOCK_BEDROCK = 5

BLOCKS: Dict[int, BlockDef] = {
    BLOCK_AIR: BlockDef(BLOCK_AIR, "Air", (0, 0, 0), (0, 0, 0), 0.0, False, False, False, None),
    BLOCK_DIRT: BlockDef(BLOCK_DIRT, "Dirt", (90, 60, 25), NEON_ORANGE, 0.24, True),
    BLOCK_STONE: BlockDef(BLOCK_STONE, "Stone", (60, 70, 90), NEON_BLUE, 0.65, True),
    BLOCK_ORE: BlockDef(BLOCK_ORE, "Ore", (50, 100, 130), NEON_CYAN, 0.95, True),
    BLOCK_WOOD: BlockDef(BLOCK_WOOD, "Wood", (30, 90, 40), NEON_GREEN, 0.38, True),
    BLOCK_BEDROCK: BlockDef(
        BLOCK_BEDROCK, "Bedrock", (80, 0, 0), NEON_RED, 9999.0, True, True, True
    ),
}


@dataclass
class ItemStack:
    block_id: int
    count: int

    def to_dict(self) -> Dict[str, int]:
        return {"block_id": self.block_id, "count": self.count}

    @staticmethod
    def from_dict(data: Dict[str, int]) -> "ItemStack":
        return ItemStack(block_id=data["block_id"], count=data["count"])


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    color: Tuple[int, int, int]
    size: float
    prev_x: float
    prev_y: float

    def update(self, dt: float) -> None:
        self.prev_x, self.prev_y = self.x, self.y
        self.vy += 800.0 * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt

    def draw(self, surface: pygame.Surface, camera: pygame.Vector2) -> None:
        if self.life <= 0:
            return
        alpha = int(255 * max(self.life / self.max_life, 0.0))
        sx = int(self.x - camera.x)
        sy = int(self.y - camera.y)
        tx = int(self.prev_x - camera.x)
        ty = int(self.prev_y - camera.y)
        trail = pygame.Surface((surface.get_width(), surface.get_height()), pygame.SRCALPHA)
        pygame.draw.line(
            trail, (*self.color, alpha // 2), (tx, ty), (sx, sy), max(1, int(self.size))
        )
        pygame.draw.circle(trail, (*self.color, alpha), (sx, sy), max(1, int(self.size)))
        surface.blit(trail, (0, 0))


class Recipe(TypedDict):
    name: str
    inputs: List[Tuple[int, int]]
    output: Tuple[int, int]


def _as_int(value: object, default: int) -> int:
    if isinstance(value, int):
        return value
    return default


class Inventory:
    def __init__(self) -> None:
        self.slots: List[Optional[ItemStack]] = [None for _ in range(27)]
        self.selected_hotbar = 0
        self.dragging: Optional[ItemStack] = None

        self.add_item(BLOCK_DIRT, 48)
        self.add_item(BLOCK_STONE, 16)
        self.add_item(BLOCK_WOOD, 16)

    def add_item(self, block_id: int, count: int) -> bool:
        if block_id == BLOCK_AIR or count <= 0:
            return False
        remaining = count
        for stack in self.slots:
            if stack and stack.block_id == block_id and stack.count < 999:
                add = min(999 - stack.count, remaining)
                stack.count += add
                remaining -= add
                if remaining == 0:
                    return True
        for i, stack in enumerate(self.slots):
            if stack is None:
                add = min(999, remaining)
                self.slots[i] = ItemStack(block_id, add)
                remaining -= add
                if remaining == 0:
                    return True
        return remaining == 0

    def consume_selected(self, amount: int = 1) -> Optional[int]:
        slot = self.selected_hotbar
        stack = self.slots[slot]
        if stack is None or stack.count < amount:
            return None
        block_id = stack.block_id
        stack.count -= amount
        if stack.count == 0:
            self.slots[slot] = None
        return block_id

    def get_selected_block(self) -> Optional[int]:
        stack = self.slots[self.selected_hotbar]
        if stack is None:
            return None
        if not BLOCKS[stack.block_id].placeable:
            return None
        return stack.block_id

    def has_items(self, block_id: int, count: int) -> bool:
        total = 0
        for stack in self.slots:
            if stack and stack.block_id == block_id:
                total += stack.count
        return total >= count

    def remove_items(self, block_id: int, count: int) -> bool:
        if not self.has_items(block_id, count):
            return False
        remaining = count
        for i, stack in enumerate(self.slots):
            if not stack or stack.block_id != block_id:
                continue
            take = min(stack.count, remaining)
            stack.count -= take
            remaining -= take
            if stack.count == 0:
                self.slots[i] = None
            if remaining == 0:
                break
        return True

    def slot_from_point(self, x: int, y: int, panel_rect: pygame.Rect, full: bool) -> Optional[int]:
        slot_size = 52
        pad = 8
        cols = 9
        rows = 3 if full else 1
        sx = panel_rect.x + 20
        sy = (
            panel_rect.y
            + panel_rect.height
            - (slot_size + 20 if not full else rows * (slot_size + pad) + 20)
        )
        for row in range(rows):
            for col in range(cols):
                idx = row * cols + col
                rect = pygame.Rect(
                    sx + col * (slot_size + pad), sy + row * (slot_size + pad), slot_size, slot_size
                )
                if rect.collidepoint(x, y):
                    return idx
        return None

    def click_slot(self, index: int) -> None:
        existing = self.slots[index]
        if self.dragging is None:
            if existing is not None:
                self.dragging = existing
                self.slots[index] = None
            return

        if existing is None:
            self.slots[index] = self.dragging
            self.dragging = None
            return

        if existing.block_id == self.dragging.block_id and existing.count < 999:
            add = min(999 - existing.count, self.dragging.count)
            existing.count += add
            self.dragging.count -= add
            if self.dragging.count <= 0:
                self.dragging = None
        else:
            self.slots[index], self.dragging = self.dragging, existing

    def to_dict(self) -> Dict[str, object]:
        return {
            "selected_hotbar": self.selected_hotbar,
            "slots": [slot.to_dict() if slot else None for slot in self.slots],
        }

    def from_dict(self, data: Dict[str, object]) -> None:
        self.selected_hotbar = _as_int(data.get("selected_hotbar", 0), 0)
        raw_slots = data.get("slots", [])
        if not isinstance(raw_slots, list):
            raw_slots = []
        self.slots = []
        for entry in raw_slots:
            if entry is None:
                self.slots.append(None)
            else:
                self.slots.append(ItemStack.from_dict(cast(Dict[str, int], entry)))
        if len(self.slots) < 27:
            self.slots.extend([None] * (27 - len(self.slots)))
        self.slots = self.slots[:27]


class World:
    def __init__(self, seed: Optional[int] = None) -> None:
        self.seed = seed if seed is not None else random.randint(0, 999_999_999)
        self.chunk_size = CHUNK_SIZE
        self.height = WORLD_HEIGHT
        self.base_surface = 72
        self.chunks: Dict[int, Dict[Tuple[int, int], int]] = {}

    def _noise(self, x: float, scale: float, salt: float) -> float:
        v = x / scale
        a = math.sin(v * 1.41 + (self.seed + salt) * 0.0013)
        b = math.sin(v * 0.49 + (self.seed + salt * 2.0) * 0.00071)
        c = math.cos(v * 2.21 + (self.seed - salt) * 0.00191)
        return (a * 0.6 + b * 0.3 + c * 0.1 + 1.0) * 0.5

    def _surface_height(self, wx: int) -> int:
        macro = self._noise(wx, 130.0, 110.0)
        medium = self._noise(wx, 48.0, 321.0)
        detail = self._noise(wx, 18.0, 690.0)
        height = self.base_surface + int(
            (macro - 0.5) * 26 + (medium - 0.5) * 14 + (detail - 0.5) * 7
        )
        return max(22, min(self.height - 24, height))

    def _cave_noise(self, wx: int, wy: int) -> float:
        a = math.sin(wx * 0.081 + self.seed * 0.0041)
        b = math.cos(wy * 0.095 - self.seed * 0.0037)
        c = math.sin((wx + wy) * 0.061 + self.seed * 0.0027)
        return (a + b + c + 3.0) / 6.0

    def _ore_noise(self, wx: int, wy: int) -> float:
        a = math.sin(wx * 0.19 + self.seed * 0.0053)
        b = math.cos(wy * 0.17 - self.seed * 0.0044)
        c = math.cos((wx - wy) * 0.083 + self.seed * 0.0019)
        return (a + b + c + 3.0) / 6.0

    def _tree_noise(self, wx: int) -> float:
        return self._noise(wx, 13.0, 999.0)

    def generate_chunk(self, chunk_x: int) -> None:
        if chunk_x in self.chunks:
            return

        blocks: Dict[Tuple[int, int], int] = {}
        x0 = chunk_x * self.chunk_size
        x1 = x0 + self.chunk_size
        surfaces: Dict[int, int] = {}

        for wx in range(x0, x1):
            surface = self._surface_height(wx)
            surfaces[wx] = surface
            for wy in range(surface, self.height):
                block_id = BLOCK_STONE

                if wy == self.height - 1:
                    block_id = BLOCK_BEDROCK
                elif wy <= surface + 2:
                    block_id = BLOCK_DIRT

                if wy > surface + 5:
                    cave = self._cave_noise(wx, wy)
                    if cave > 0.75:
                        continue
                    ore = self._ore_noise(wx, wy)
                    if ore > 0.82 and wy > self.base_surface + 5:
                        block_id = BLOCK_ORE

                blocks[(wx, wy)] = block_id

        for wx in range(x0, x1):
            surface = surfaces[wx]
            if self._tree_noise(wx) > 0.84 and self._tree_noise(wx + 1) < 0.6:
                trunk_h = 3 + int(self._tree_noise(wx * 2) * 3)
                for i in range(trunk_h):
                    wy = surface - 1 - i
                    if wy > 2:
                        blocks[(wx, wy)] = BLOCK_WOOD
                crown_y = surface - 1 - trunk_h
                for ox in range(-2, 3):
                    for oy in range(-2, 2):
                        if abs(ox) + abs(oy) > 3:
                            continue
                        lx = wx + ox
                        ly = crown_y + oy
                        if ly > 1:
                            blocks[(lx, ly)] = BLOCK_WOOD

        self.chunks[chunk_x] = blocks

    def ensure_chunks(self, min_chunk: int, max_chunk: int) -> None:
        for cx in range(min_chunk, max_chunk + 1):
            self.generate_chunk(cx)

    def get_block(self, wx: int, wy: int) -> int:
        if wy < 0 or wy >= self.height:
            return BLOCK_AIR
        cx = math.floor(wx / self.chunk_size)
        self.generate_chunk(cx)
        return self.chunks[cx].get((wx, wy), BLOCK_AIR)

    def set_block(self, wx: int, wy: int, block_id: int) -> None:
        if wy < 0 or wy >= self.height:
            return
        cx = math.floor(wx / self.chunk_size)
        self.generate_chunk(cx)
        key = (wx, wy)
        if block_id == BLOCK_AIR:
            self.chunks[cx].pop(key, None)
        else:
            self.chunks[cx][key] = block_id

    def iter_visible_blocks(
        self, min_wx: int, max_wx: int, min_wy: int, max_wy: int
    ) -> Iterable[Tuple[int, int, int]]:
        min_cx = math.floor(min_wx / self.chunk_size)
        max_cx = math.floor(max_wx / self.chunk_size)
        self.ensure_chunks(min_cx, max_cx)
        for cx in range(min_cx, max_cx + 1):
            for (wx, wy), block_id in self.chunks[cx].items():
                if min_wx <= wx <= max_wx and min_wy <= wy <= max_wy:
                    yield wx, wy, block_id

    def to_dict(self) -> Dict[str, object]:
        serialized_chunks: Dict[str, List[List[int]]] = {}
        for cx, chunk in self.chunks.items():
            serialized_chunks[str(cx)] = [
                [wx, wy, block_id] for (wx, wy), block_id in chunk.items()
            ]
        return {
            "seed": self.seed,
            "chunk_size": self.chunk_size,
            "height": self.height,
            "chunks": serialized_chunks,
        }

    @staticmethod
    def from_dict(data: Dict[str, object]) -> "World":
        world = World(seed=_as_int(data.get("seed", random.randint(0, 999_999)), 0))
        world.chunk_size = _as_int(data.get("chunk_size", CHUNK_SIZE), CHUNK_SIZE)
        world.height = _as_int(data.get("height", WORLD_HEIGHT), WORLD_HEIGHT)
        world.chunks = {}

        raw_chunks = data.get("chunks", {})
        if isinstance(raw_chunks, dict):
            for key, entries in raw_chunks.items():
                cx = int(key)
                chunk: Dict[Tuple[int, int], int] = {}
                if isinstance(entries, list):
                    for entry in entries:
                        if isinstance(entry, list) and len(entry) == 3:
                            wx, wy, block_id = int(entry[0]), int(entry[1]), int(entry[2])
                            chunk[(wx, wy)] = block_id
                world.chunks[cx] = chunk
        return world


class Player:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.width = int(TILE_SIZE * 0.72)
        self.height = int(TILE_SIZE * 1.62)
        self.vx = 0.0
        self.vy = 0.0
        self.speed = 290.0
        self.accel_ground = 11.5
        self.accel_air = 6.5
        self.friction = 9.5
        self.gravity = 1320.0
        self.jump_force = 545.0
        self.on_ground = False
        self.facing = 1
        self.walk_cycle = 0.0

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.width, self.height)

    def _solid_at(self, world: World, wx: int, wy: int) -> bool:
        block = world.get_block(wx, wy)
        return BLOCKS[block].solid

    def _collect_solid_tiles(self, world: World, rect: pygame.Rect) -> List[pygame.Rect]:
        min_tx = math.floor(rect.left / TILE_SIZE)
        max_tx = math.floor((rect.right - 1) / TILE_SIZE)
        min_ty = math.floor(rect.top / TILE_SIZE)
        max_ty = math.floor((rect.bottom - 1) / TILE_SIZE)

        solids: List[pygame.Rect] = []
        for tx in range(min_tx, max_tx + 1):
            for ty in range(min_ty, max_ty + 1):
                if self._solid_at(world, tx, ty):
                    solids.append(pygame.Rect(tx * TILE_SIZE, ty * TILE_SIZE, TILE_SIZE, TILE_SIZE))
        return solids

    def update(self, world: World, dt: float, keys: pygame.key.ScancodeWrapper) -> None:
        left = keys[pygame.K_a] or keys[pygame.K_LEFT]
        right = keys[pygame.K_d] or keys[pygame.K_RIGHT]
        jump = keys[pygame.K_w] or keys[pygame.K_UP] or keys[pygame.K_SPACE]

        move_input = float(right) - float(left)
        target_vx = move_input * self.speed
        accel = self.accel_ground if self.on_ground else self.accel_air
        self.vx += (target_vx - self.vx) * min(1.0, accel * dt)

        if abs(move_input) < 0.01 and self.on_ground:
            self.vx *= max(0.0, 1.0 - self.friction * dt)
            if abs(self.vx) < 4.0:
                self.vx = 0.0

        if jump and self.on_ground:
            self.vy = -self.jump_force
            self.on_ground = False

        self.vy += self.gravity * dt
        self.vy = min(self.vy, 1200.0)

        self.x += self.vx * dt
        rect = self.rect
        for tile in self._collect_solid_tiles(world, rect):
            if rect.colliderect(tile):
                if self.vx > 0:
                    rect.right = tile.left
                elif self.vx < 0:
                    rect.left = tile.right
                self.x = rect.x
                self.vx = 0.0

        self.y += self.vy * dt
        rect = self.rect
        self.on_ground = False
        for tile in self._collect_solid_tiles(world, rect):
            if rect.colliderect(tile):
                if self.vy > 0:
                    rect.bottom = tile.top
                    self.on_ground = True
                elif self.vy < 0:
                    rect.top = tile.bottom
                self.y = rect.y
                self.vy = 0.0

        if move_input != 0:
            self.facing = 1 if move_input > 0 else -1
            self.walk_cycle += dt * 9.0 * abs(move_input)

    def to_dict(self) -> Dict[str, float]:
        return {"x": self.x, "y": self.y, "vx": self.vx, "vy": self.vy}

    def from_dict(self, data: Dict[str, float]) -> None:
        self.x = float(data.get("x", self.x))
        self.y = float(data.get("y", self.y))
        self.vx = float(data.get("vx", 0.0))
        self.vy = float(data.get("vy", 0.0))
