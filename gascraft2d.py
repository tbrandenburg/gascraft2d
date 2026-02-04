from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

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
    BLOCK_BEDROCK: BlockDef(BLOCK_BEDROCK, "Bedrock", (80, 0, 0), NEON_RED, 9999.0, True, True, True),
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
        pygame.draw.line(trail, (*self.color, alpha // 2), (tx, ty), (sx, sy), max(1, int(self.size)))
        pygame.draw.circle(trail, (*self.color, alpha), (sx, sy), max(1, int(self.size)))
        surface.blit(trail, (0, 0))


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
        sy = panel_rect.y + panel_rect.height - (slot_size + 20 if not full else rows * (slot_size + pad) + 20)
        for row in range(rows):
            for col in range(cols):
                idx = row * cols + col
                rect = pygame.Rect(sx + col * (slot_size + pad), sy + row * (slot_size + pad), slot_size, slot_size)
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
        self.selected_hotbar = int(data.get("selected_hotbar", 0))
        raw_slots = data.get("slots", [])
        self.slots = []
        for entry in raw_slots:
            if entry is None:
                self.slots.append(None)
            else:
                self.slots.append(ItemStack.from_dict(entry))
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
        height = self.base_surface + int((macro - 0.5) * 26 + (medium - 0.5) * 14 + (detail - 0.5) * 7)
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
            serialized_chunks[str(cx)] = [[wx, wy, block_id] for (wx, wy), block_id in chunk.items()]
        return {
            "seed": self.seed,
            "chunk_size": self.chunk_size,
            "height": self.height,
            "chunks": serialized_chunks,
        }

    @staticmethod
    def from_dict(data: Dict[str, object]) -> "World":
        world = World(seed=int(data.get("seed", random.randint(0, 999_999))))
        world.chunk_size = int(data.get("chunk_size", CHUNK_SIZE))
        world.height = int(data.get("height", WORLD_HEIGHT))
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


class Game:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Gascraft2D - Neon Voxel Frontier")
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 20)
        self.big_font = pygame.font.SysFont("consolas", 34, bold=True)

        self.world = World()
        self.player = Player(0.0, 0.0)
        self.inventory = Inventory()
        self.particles: List[Particle] = []

        self.camera = pygame.Vector2(0.0, 0.0)
        self.running = True
        self.show_inventory = False
        self.show_menu = False
        self.show_crafting = False

        self.day_timer = 0.0
        self.day_length = 140.0

        self.mining_target: Optional[Tuple[int, int]] = None
        self.mining_progress = 0.0
        self.last_mouse_left = False
        self.last_mouse_right = False

        self.recipes = [
            {"name": "Compacted Stone", "inputs": [(BLOCK_DIRT, 4)], "output": (BLOCK_STONE, 1)},
            {"name": "Refined Ore", "inputs": [(BLOCK_STONE, 3), (BLOCK_ORE, 1)], "output": (BLOCK_ORE, 2)},
        ]

        self.new_world()

    # --- Utility ------------------------------------------------------------
    def lerp_color(self, c1: Tuple[int, int, int], c2: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
        t = max(0.0, min(1.0, t))
        return (
            int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t),
        )

    def glow_rect(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        color: Tuple[int, int, int],
        core_alpha: int = 180,
        glow_alpha: int = 60,
    ) -> None:
        glow = pygame.Surface((rect.width + 20, rect.height + 20), pygame.SRCALPHA)
        center = pygame.Rect(10, 10, rect.width, rect.height)
        for i, a in enumerate((glow_alpha // 2, glow_alpha, glow_alpha * 2)):
            expanded = center.inflate(i * 6 + 6, i * 6 + 6)
            pygame.draw.rect(glow, (*color, max(10, min(150, a))), expanded, border_radius=4)
        pygame.draw.rect(glow, (*color, core_alpha), center, width=2, border_radius=3)
        surface.blit(glow, (rect.x - 10, rect.y - 10), special_flags=pygame.BLEND_ALPHA_SDL2)

    def block_to_screen(self, wx: int, wy: int) -> Tuple[int, int]:
        return int(wx * TILE_SIZE - self.camera.x), int(wy * TILE_SIZE - self.camera.y)

    def screen_to_block(self, sx: int, sy: int) -> Tuple[int, int]:
        wx = math.floor((sx + self.camera.x) / TILE_SIZE)
        wy = math.floor((sy + self.camera.y) / TILE_SIZE)
        return wx, wy

    def player_block_pos(self) -> Tuple[int, int]:
        return (
            math.floor((self.player.x + self.player.width * 0.5) / TILE_SIZE),
            math.floor((self.player.y + self.player.height * 0.5) / TILE_SIZE),
        )

    # --- World lifecycle ----------------------------------------------------
    def new_world(self) -> None:
        self.world = World()
        spawn_x = 0
        surface = self.world._surface_height(spawn_x)
        self.player = Player(spawn_x * TILE_SIZE, (surface - 4) * TILE_SIZE)
        self.inventory = Inventory()
        self.camera.xy = (self.player.x - self.screen.get_width() / 2, self.player.y - self.screen.get_height() / 2)
        self.particles.clear()

    def save_game(self) -> None:
        data = {
            "world": self.world.to_dict(),
            "player": self.player.to_dict(),
            "inventory": self.inventory.to_dict(),
            "day_timer": self.day_timer,
        }
        SAVE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_game(self) -> bool:
        if not SAVE_PATH.exists():
            return False
        data = json.loads(SAVE_PATH.read_text(encoding="utf-8"))
        self.world = World.from_dict(data.get("world", {}))
        self.player = Player(0.0, 0.0)
        self.player.from_dict(data.get("player", {}))
        self.inventory = Inventory()
        self.inventory.from_dict(data.get("inventory", {}))
        self.day_timer = float(data.get("day_timer", 0.0))
        self.camera.xy = (self.player.x - self.screen.get_width() / 2, self.player.y - self.screen.get_height() / 2)
        return True

    # --- Input & gameplay ---------------------------------------------------
    def spawn_mine_particles(self, wx: int, wy: int, block_id: int) -> None:
        base_x = wx * TILE_SIZE + TILE_SIZE * 0.5
        base_y = wy * TILE_SIZE + TILE_SIZE * 0.5
        for _ in range(18):
            angle = random.random() * math.tau
            speed = random.uniform(70.0, 260.0)
            color = BLOCKS[block_id].glow
            self.particles.append(
                Particle(
                    x=base_x + random.uniform(-8, 8),
                    y=base_y + random.uniform(-8, 8),
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed - 120,
                    life=random.uniform(0.2, 0.8),
                    max_life=0.8,
                    color=color,
                    size=random.uniform(1.8, 3.8),
                    prev_x=base_x,
                    prev_y=base_y,
                )
            )

    def can_reach(self, wx: int, wy: int) -> bool:
        px, py = self.player_block_pos()
        return abs(wx - px) <= 8 and abs(wy - py) <= 8

    def handle_mining_and_placing(self, dt: float, mouse_pos: Tuple[int, int], mouse_buttons: Tuple[bool, bool, bool]) -> None:
        left = mouse_buttons[0]
        right = mouse_buttons[2]
        target_wx, target_wy = self.screen_to_block(*mouse_pos)

        # Mining
        if left and not self.show_inventory and not self.show_menu and not self.show_crafting:
            if self.can_reach(target_wx, target_wy):
                block_id = self.world.get_block(target_wx, target_wy)
                block = BLOCKS[block_id]
                if block_id != BLOCK_AIR and not block.unbreakable:
                    if self.mining_target != (target_wx, target_wy):
                        self.mining_target = (target_wx, target_wy)
                        self.mining_progress = 0.0
                    self.mining_progress += dt / max(0.05, block.break_time)
                    if self.mining_progress >= 1.0:
                        self.world.set_block(target_wx, target_wy, BLOCK_AIR)
                        if block.drop_id is None:
                            self.inventory.add_item(block_id, 1)
                        else:
                            self.inventory.add_item(block.drop_id, 1)
                        self.spawn_mine_particles(target_wx, target_wy, block_id)
                        self.mining_progress = 0.0
                        self.mining_target = None
                else:
                    self.mining_target = None
                    self.mining_progress = 0.0
            else:
                self.mining_target = None
                self.mining_progress = 0.0
        else:
            if not left:
                self.mining_target = None
                self.mining_progress = 0.0

        # Placement (edge triggered)
        if right and not self.last_mouse_right and not self.show_inventory and not self.show_menu and not self.show_crafting:
            if self.can_reach(target_wx, target_wy) and self.world.get_block(target_wx, target_wy) == BLOCK_AIR:
                selected = self.inventory.get_selected_block()
                if selected is not None:
                    place_rect = pygame.Rect(target_wx * TILE_SIZE, target_wy * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                    if not place_rect.colliderect(self.player.rect):
                        consumed = self.inventory.consume_selected(1)
                        if consumed is not None:
                            self.world.set_block(target_wx, target_wy, consumed)

        self.last_mouse_left = left
        self.last_mouse_right = right

    def craft(self, recipe_index: int) -> bool:
        if recipe_index < 0 or recipe_index >= len(self.recipes):
            return False
        recipe = self.recipes[recipe_index]
        for block_id, count in recipe["inputs"]:
            if not self.inventory.has_items(block_id, count):
                return False
        for block_id, count in recipe["inputs"]:
            self.inventory.remove_items(block_id, count)
        out_id, out_count = recipe["output"]
        self.inventory.add_item(out_id, out_count)
        return True

    # --- Rendering ----------------------------------------------------------
    def sky_colors(self) -> Tuple[Tuple[int, int, int], Tuple[int, int, int], float]:
        t = (math.sin(self.day_timer / self.day_length * math.tau) + 1.0) * 0.5
        top_day = (10, 40, 80)
        top_night = (4, 8, 20)
        top_dusk = (50, 8, 60)

        bot_day = (20, 120, 170)
        bot_night = (8, 12, 35)
        bot_dusk = (120, 20, 100)

        dusk_weight = abs(t - 0.5) * 2.0
        dusk_weight = 1.0 - min(1.0, dusk_weight)

        top_mix = self.lerp_color(top_day, top_night, 1.0 - t)
        bot_mix = self.lerp_color(bot_day, bot_night, 1.0 - t)
        top = self.lerp_color(top_mix, top_dusk, dusk_weight * 0.8)
        bottom = self.lerp_color(bot_mix, bot_dusk, dusk_weight * 0.8)

        night_factor = 1.0 - t
        return top, bottom, night_factor

    def draw_background(self) -> float:
        w, h = self.screen.get_size()
        top, bottom, night_factor = self.sky_colors()

        bg = pygame.Surface((w, h))
        for y in range(h):
            t = y / max(1, h - 1)
            color = self.lerp_color(top, bottom, t)
            pygame.draw.line(bg, color, (0, y), (w, y))

        spacing = 46
        grid = pygame.Surface((w, h), pygame.SRCALPHA)
        ox = int((-self.camera.x * 0.3) % spacing)
        oy = int((-self.camera.y * 0.2) % spacing)
        grid_color = (*NEON_CYAN, int(34 + night_factor * 30))
        for x in range(-spacing, w + spacing, spacing):
            pygame.draw.line(grid, grid_color, (x + ox, 0), (x + ox, h), 1)
        for y in range(-spacing, h + spacing, spacing):
            pygame.draw.line(grid, grid_color, (0, y + oy), (w, y + oy), 1)

        self.screen.blit(bg, (0, 0))
        self.screen.blit(grid, (0, 0))
        return night_factor

    def draw_block(self, sx: int, sy: int, block_id: int, night_factor: float, tick: float) -> None:
        block = BLOCKS[block_id]
        rect = pygame.Rect(sx, sy, TILE_SIZE, TILE_SIZE)

        if block_id == BLOCK_ORE:
            pulse = 0.55 + 0.45 * math.sin(tick * 8.0 + (sx + sy) * 0.02)
            base = self.lerp_color(block.color, NEON_MAGENTA, pulse * 0.5)
            pygame.draw.rect(self.screen, base, rect)
            sparkle = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
            for _ in range(4):
                px = random.randint(2, TILE_SIZE - 3)
                py = random.randint(2, TILE_SIZE - 3)
                pygame.draw.circle(sparkle, (*NEON_CYAN, int(100 + 155 * pulse)), (px, py), 1)
            self.screen.blit(sparkle, (sx, sy))
        else:
            pygame.draw.rect(self.screen, block.color, rect)

        glow_amount = int(90 + 120 * night_factor)
        self.glow_rect(self.screen, rect, block.glow, core_alpha=150, glow_alpha=glow_amount)

        edge = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
        pygame.draw.rect(edge, (*block.glow, 120), edge.get_rect(), width=1)
        self.screen.blit(edge, (sx, sy))

    def draw_world(self, dt: float, night_factor: float) -> None:
        w, h = self.screen.get_size()
        min_wx = math.floor(self.camera.x / TILE_SIZE) - 2
        max_wx = math.floor((self.camera.x + w) / TILE_SIZE) + 2
        min_wy = max(0, math.floor(self.camera.y / TILE_SIZE) - 2)
        max_wy = min(self.world.height - 1, math.floor((self.camera.y + h) / TILE_SIZE) + 2)

        tick = pygame.time.get_ticks() * 0.001
        for wx, wy, block_id in self.world.iter_visible_blocks(min_wx, max_wx, min_wy, max_wy):
            if block_id == BLOCK_AIR:
                continue
            sx, sy = self.block_to_screen(wx, wy)
            self.draw_block(sx, sy, block_id, night_factor, tick)

        if self.mining_target is not None:
            tx, ty = self.mining_target
            sx, sy = self.block_to_screen(tx, ty)
            if -TILE_SIZE <= sx <= w and -TILE_SIZE <= sy <= h:
                a = int(50 + 180 * self.mining_progress)
                crack = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
                for i in range(4):
                    pygame.draw.line(
                        crack,
                        (*NEON_YELLOW, a),
                        (2 + i * 7, 3),
                        (TILE_SIZE - 3 - i * 5, TILE_SIZE - 4),
                        1,
                    )
                self.screen.blit(crack, (sx, sy))

    def draw_player(self, night_factor: float) -> None:
        rect = self.player.rect.move(-int(self.camera.x), -int(self.camera.y))
        body = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)

        swing = math.sin(self.player.walk_cycle) * 3.0 * min(1.0, abs(self.player.vx) / max(1.0, self.player.speed))
        pygame.draw.rect(body, (25, 30, 60), (0, 0, rect.width, rect.height), border_radius=5)
        pygame.draw.rect(body, (*NEON_CYAN, 150), (0, 0, rect.width, rect.height), width=2, border_radius=5)
        eye_y = rect.height // 3
        eye_x = rect.width // 2 + int(swing)
        pygame.draw.circle(body, (*NEON_MAGENTA, 220), (eye_x, eye_y), 3)

        self.screen.blit(body, rect.topleft)
        glow_rect = rect.inflate(16, 16)
        self.glow_rect(self.screen, glow_rect, NEON_CYAN, core_alpha=90, glow_alpha=int(70 + 60 * night_factor))

    def draw_particles(self) -> None:
        for particle in self.particles:
            particle.draw(self.screen, self.camera)

    def draw_hotbar(self) -> None:
        w, h = self.screen.get_size()
        slot_size = 52
        pad = 8
        total_w = 9 * slot_size + 8 * pad + 40
        panel = pygame.Rect((w - total_w) // 2, h - 92, total_w, 76)
        pygame.draw.rect(self.screen, (6, 12, 28, 180), panel, border_radius=8)
        self.glow_rect(self.screen, panel, NEON_CYAN, core_alpha=120, glow_alpha=45)

        sx = panel.x + 20
        sy = panel.y + 12
        for i in range(9):
            slot_rect = pygame.Rect(sx + i * (slot_size + pad), sy, slot_size, slot_size)
            color = NEON_MAGENTA if i == self.inventory.selected_hotbar else NEON_CYAN
            pygame.draw.rect(self.screen, (8, 18, 36), slot_rect, border_radius=6)
            self.glow_rect(self.screen, slot_rect, color, core_alpha=140, glow_alpha=55)

            stack = self.inventory.slots[i]
            if stack:
                self.draw_item_icon(slot_rect, stack)

            key_label = self.font.render(str(i + 1), True, color)
            self.screen.blit(key_label, (slot_rect.x + 3, slot_rect.y + 2))

    def draw_item_icon(self, slot_rect: pygame.Rect, stack: ItemStack) -> None:
        block = BLOCKS[stack.block_id]
        icon = pygame.Rect(slot_rect.x + 10, slot_rect.y + 8, slot_rect.width - 20, slot_rect.height - 20)
        pygame.draw.rect(self.screen, block.color, icon, border_radius=3)
        pygame.draw.rect(self.screen, block.glow, icon, width=2, border_radius=3)
        count_text = self.font.render(str(stack.count), True, block.glow)
        self.screen.blit(count_text, (slot_rect.right - count_text.get_width() - 4, slot_rect.bottom - count_text.get_height() - 3))

    def draw_inventory_panel(self) -> pygame.Rect:
        w, h = self.screen.get_size()
        panel = pygame.Rect(w // 2 - 320, h // 2 - 250, 640, 500)
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        self.screen.blit(overlay, (0, 0))

        pygame.draw.rect(self.screen, (7, 14, 30), panel, border_radius=10)
        self.glow_rect(self.screen, panel, NEON_CYAN, core_alpha=180, glow_alpha=75)
        title = self.big_font.render("INVENTORY", True, NEON_CYAN)
        self.screen.blit(title, (panel.x + 20, panel.y + 14))

        slot_size = 52
        pad = 8
        sx = panel.x + 20
        sy = panel.y + 90
        for row in range(3):
            for col in range(9):
                idx = row * 9 + col
                slot_rect = pygame.Rect(sx + col * (slot_size + pad), sy + row * (slot_size + pad), slot_size, slot_size)
                color = NEON_MAGENTA if idx == self.inventory.selected_hotbar else NEON_CYAN
                pygame.draw.rect(self.screen, (8, 18, 36), slot_rect, border_radius=6)
                self.glow_rect(self.screen, slot_rect, color, core_alpha=125, glow_alpha=42)
                stack = self.inventory.slots[idx]
                if stack:
                    self.draw_item_icon(slot_rect, stack)

        tip = self.font.render("Click to move stacks. E/I closes.", True, NEON_YELLOW)
        self.screen.blit(tip, (panel.x + 20, panel.bottom - 36))

        if self.inventory.dragging:
            mx, my = pygame.mouse.get_pos()
            drag_rect = pygame.Rect(mx - 20, my - 20, 42, 42)
            self.draw_item_icon(drag_rect.inflate(10, 10), self.inventory.dragging)

        return panel

    def draw_menu(self) -> None:
        w, h = self.screen.get_size()
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        panel = pygame.Rect(w // 2 - 240, h // 2 - 190, 480, 380)
        pygame.draw.rect(self.screen, (8, 14, 30), panel, border_radius=10)
        self.glow_rect(self.screen, panel, NEON_MAGENTA, core_alpha=170, glow_alpha=80)
        title = self.big_font.render("SYSTEM MENU", True, NEON_MAGENTA)
        self.screen.blit(title, (panel.x + 108, panel.y + 24))

        options = [
            "F5 - Save World",
            "F9 - Load World",
            "N  - New World",
            "ESC - Resume",
            "C  - Crafting",
        ]
        for i, text in enumerate(options):
            line = self.font.render(text, True, NEON_CYAN if i % 2 == 0 else NEON_YELLOW)
            self.screen.blit(line, (panel.x + 60, panel.y + 100 + i * 42))

    def draw_crafting_panel(self) -> pygame.Rect:
        w, h = self.screen.get_size()
        panel = pygame.Rect(w // 2 - 300, h // 2 - 220, 600, 440)
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))

        pygame.draw.rect(self.screen, (8, 16, 34), panel, border_radius=10)
        self.glow_rect(self.screen, panel, NEON_GREEN, core_alpha=160, glow_alpha=70)
        title = self.big_font.render("CRAFTING MATRIX", True, NEON_GREEN)
        self.screen.blit(title, (panel.x + 140, panel.y + 20))

        for i, recipe in enumerate(self.recipes):
            row = pygame.Rect(panel.x + 30, panel.y + 90 + i * 120, panel.width - 60, 92)
            pygame.draw.rect(self.screen, (7, 18, 32), row, border_radius=8)
            self.glow_rect(self.screen, row, NEON_CYAN, core_alpha=110, glow_alpha=40)
            txt = self.font.render(recipe["name"], True, NEON_YELLOW)
            self.screen.blit(txt, (row.x + 12, row.y + 10))

            needs = " + ".join(f"{count} {BLOCKS[b].name}" for b, count in recipe["inputs"])
            out_id, out_count = recipe["output"]
            out_text = f"=> {out_count} {BLOCKS[out_id].name}"
            can_craft = all(self.inventory.has_items(b, c) for b, c in recipe["inputs"])
            line1 = self.font.render(needs, True, NEON_CYAN)
            line2 = self.font.render(out_text, True, NEON_GREEN if can_craft else NEON_MAGENTA)
            self.screen.blit(line1, (row.x + 12, row.y + 40))
            self.screen.blit(line2, (row.x + 12, row.y + 63))

            button = pygame.Rect(row.right - 110, row.y + 26, 92, 38)
            pygame.draw.rect(self.screen, (15, 30, 45), button, border_radius=6)
            self.glow_rect(self.screen, button, NEON_GREEN if can_craft else NEON_MAGENTA, core_alpha=120, glow_alpha=45)
            bt = self.font.render("CRAFT", True, NEON_YELLOW if can_craft else (180, 80, 180))
            self.screen.blit(bt, (button.x + 18, button.y + 8))

        hint = self.font.render("Click CRAFT. Press C to close.", True, NEON_CYAN)
        self.screen.blit(hint, (panel.x + 24, panel.bottom - 34))
        return panel

    def draw_hud(self) -> None:
        px, py = self.player_block_pos()
        time_phase = (self.day_timer / self.day_length) % 1.0
        info = f"XYZ: {px}, {py}  |  Seed: {self.world.seed}  |  Time: {time_phase:.2f}"
        text = self.font.render(info, True, NEON_CYAN)
        shadow = self.font.render(info, True, (0, 0, 0))
        self.screen.blit(shadow, (14, 14))
        self.screen.blit(text, (12, 12))

        controls = "WASD/Arrows Move | LMB Mine | RMB Place | E Inventory | C Craft | ESC Menu"
        ctext = self.font.render(controls, True, NEON_YELLOW)
        self.screen.blit(ctext, (12, 40))

    # --- Main loop ----------------------------------------------------------
    def process_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
            elif event.type == pygame.KEYDOWN:
                if pygame.K_1 <= event.key <= pygame.K_9:
                    self.inventory.selected_hotbar = event.key - pygame.K_1
                elif event.key in (pygame.K_e, pygame.K_i):
                    self.show_inventory = not self.show_inventory
                    self.show_menu = False
                    self.show_crafting = False
                elif event.key == pygame.K_ESCAPE:
                    if self.show_inventory:
                        self.show_inventory = False
                    elif self.show_crafting:
                        self.show_crafting = False
                    else:
                        self.show_menu = not self.show_menu
                elif event.key == pygame.K_c:
                    self.show_crafting = not self.show_crafting
                    self.show_menu = False
                    self.show_inventory = False
                elif event.key == pygame.K_F5:
                    self.save_game()
                elif event.key == pygame.K_F9:
                    self.load_game()
                elif event.key == pygame.K_n:
                    self.new_world()
            elif event.type == pygame.MOUSEWHEEL:
                self.inventory.selected_hotbar = (self.inventory.selected_hotbar - event.y) % 9
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if self.show_inventory and event.button == 1:
                    panel = pygame.Rect(self.screen.get_width() // 2 - 320, self.screen.get_height() // 2 - 250, 640, 500)
                    idx = self.inventory.slot_from_point(event.pos[0], event.pos[1], panel, full=True)
                    if idx is not None:
                        self.inventory.click_slot(idx)
                if self.show_crafting and event.button == 1:
                    panel = pygame.Rect(self.screen.get_width() // 2 - 300, self.screen.get_height() // 2 - 220, 600, 440)
                    for i in range(len(self.recipes)):
                        row = pygame.Rect(panel.x + 30, panel.y + 90 + i * 120, panel.width - 60, 92)
                        button = pygame.Rect(row.right - 110, row.y + 26, 92, 38)
                        if button.collidepoint(event.pos):
                            self.craft(i)

    def update(self, dt: float) -> None:
        self.day_timer = (self.day_timer + dt) % self.day_length

        if not (self.show_menu or self.show_inventory or self.show_crafting):
            keys = pygame.key.get_pressed()
            self.player.update(self.world, dt, keys)
            mouse_pos = pygame.mouse.get_pos()
            mouse_buttons = pygame.mouse.get_pressed(3)
            self.handle_mining_and_placing(dt, mouse_pos, mouse_buttons)

        # Smooth camera follow
        target = pygame.Vector2(
            self.player.x + self.player.width * 0.5 - self.screen.get_width() * 0.5,
            self.player.y + self.player.height * 0.5 - self.screen.get_height() * 0.5,
        )
        self.camera += (target - self.camera) * min(1.0, dt * 8.0)

        self.particles = [p for p in self.particles if p.life > 0]
        for particle in self.particles:
            particle.update(dt)

    def render(self, dt: float) -> None:
        night_factor = self.draw_background()
        self.draw_world(dt, night_factor)
        self.draw_player(night_factor)
        self.draw_particles()
        self.draw_hud()
        self.draw_hotbar()

        if self.show_inventory:
            self.draw_inventory_panel()
        if self.show_menu:
            self.draw_menu()
        if self.show_crafting:
            self.draw_crafting_panel()

        pygame.display.flip()

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self.process_events()
            self.update(dt)
            self.render(dt)

        pygame.quit()


def main() -> None:
    Game().run()


if __name__ == "__main__":
    main()
