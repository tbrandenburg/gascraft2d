from __future__ import annotations

import math

import pygame

from gascraft2d.core import (
    BLOCK_AIR,
    BLOCK_DIRT,
    BLOCK_STONE,
    BLOCK_WOOD,
    CHUNK_SIZE,
    Inventory,
    ItemStack,
    Particle,
    Player,
    World,
)


class FakeKeys(dict[int, bool]):
    def __getitem__(self, key: int) -> bool:
        return self.get(key, False)


def test_itemstack_roundtrip() -> None:
    stack = ItemStack(block_id=BLOCK_STONE, count=7)
    assert ItemStack.from_dict(stack.to_dict()) == stack


def test_inventory_add_consume_and_remove_items() -> None:
    inv = Inventory()
    inv.slots = [None for _ in range(27)]

    assert inv.add_item(BLOCK_DIRT, 10)
    assert inv.has_items(BLOCK_DIRT, 10)

    inv.selected_hotbar = 0
    assert inv.consume_selected(4) == BLOCK_DIRT
    assert inv.slots[0] is not None and inv.slots[0].count == 6

    assert inv.remove_items(BLOCK_DIRT, 5)
    assert inv.slots[0] is not None and inv.slots[0].count == 1


def test_inventory_click_slot_merges_and_swaps() -> None:
    inv = Inventory()
    inv.slots = [None for _ in range(27)]
    inv.slots[0] = ItemStack(BLOCK_DIRT, 3)
    inv.slots[1] = ItemStack(BLOCK_DIRT, 5)

    inv.click_slot(0)
    assert inv.dragging is not None and inv.dragging.count == 3
    inv.click_slot(1)
    assert inv.dragging is None
    assert inv.slots[1] is not None and inv.slots[1].count == 8


def test_inventory_slot_from_point_for_hotbar() -> None:
    inv = Inventory()
    panel = pygame.Rect(100, 200, 600, 100)
    idx = inv.slot_from_point(panel.x + 25, panel.y + panel.height - 40, panel, full=False)
    assert idx == 0


def test_inventory_to_from_dict_pads_slots() -> None:
    inv = Inventory()
    inv.slots = [ItemStack(BLOCK_WOOD, 2)]
    data = inv.to_dict()

    restored = Inventory()
    restored.from_dict(data)

    assert len(restored.slots) == 27
    assert restored.slots[0] is not None and restored.slots[0].block_id == BLOCK_WOOD


def test_world_get_set_and_chunk_generation() -> None:
    world = World(seed=123)
    assert world.get_block(0, -1) == BLOCK_AIR

    world.set_block(2, 2, BLOCK_WOOD)
    assert world.get_block(2, 2) == BLOCK_WOOD

    world.set_block(2, 2, BLOCK_AIR)
    assert world.get_block(2, 2) == BLOCK_AIR

    world.generate_chunk(0)
    assert 0 in world.chunks
    assert len(world.chunks[0]) > 0


def test_world_serialization_roundtrip() -> None:
    world = World(seed=77)
    world.set_block(CHUNK_SIZE + 2, 40, BLOCK_STONE)
    payload = world.to_dict()

    restored = World.from_dict(payload)
    assert restored.seed == 77
    assert restored.get_block(CHUNK_SIZE + 2, 40) == BLOCK_STONE


def test_world_iter_visible_blocks_bounds() -> None:
    world = World(seed=5)
    world.set_block(1, 30, BLOCK_DIRT)
    world.set_block(200, 30, BLOCK_DIRT)

    blocks = list(world.iter_visible_blocks(0, 10, 20, 40))
    coords = {(wx, wy) for wx, wy, _ in blocks}
    assert (1, 30) in coords
    assert (200, 30) not in coords


def test_player_horizontal_movement() -> None:
    world = World(seed=9)
    player = Player(64.0, 64.0)

    keys = FakeKeys({pygame.K_d: True})
    player.update(world, 0.1, keys)

    assert player.vx > 0.0
    assert player.facing == 1


def test_player_lands_on_ground_block() -> None:
    world = World(seed=10)
    player = Player(64.0, 0.0)

    # Build a short floor under the player.
    floor_y = 4
    for tx in range(1, 5):
        world.set_block(tx, floor_y, BLOCK_STONE)

    grounded_once = False
    for _ in range(240):
        player.update(world, 1 / 60.0, FakeKeys())
        grounded_once = grounded_once or player.on_ground

    assert grounded_once
    assert math.isfinite(player.y)


def test_player_jump_sets_negative_vertical_velocity() -> None:
    world = World(seed=11)
    player = Player(64.0, 64.0)
    player.on_ground = True

    keys = FakeKeys({pygame.K_SPACE: True})
    player.update(world, 1 / 60.0, keys)

    assert player.vy < 0


def test_player_to_from_dict_roundtrip() -> None:
    player = Player(1.0, 2.0)
    player.vx = 3.0
    player.vy = 4.0

    data = player.to_dict()
    restored = Player(0.0, 0.0)
    restored.from_dict(data)

    assert restored.x == 1.0
    assert restored.y == 2.0
    assert restored.vx == 3.0
    assert restored.vy == 4.0


def test_particle_update_and_dead_draw_noop() -> None:
    particle = Particle(
        x=0.0,
        y=0.0,
        vx=10.0,
        vy=0.0,
        life=0.5,
        max_life=1.0,
        color=(255, 255, 255),
        size=2.0,
        prev_x=0.0,
        prev_y=0.0,
    )
    particle.update(0.1)
    assert particle.x > 0.0
    assert particle.life < 0.5

    dead = Particle(
        x=0.0,
        y=0.0,
        vx=0.0,
        vy=0.0,
        life=0.0,
        max_life=1.0,
        color=(255, 255, 255),
        size=2.0,
        prev_x=0.0,
        prev_y=0.0,
    )
    surface = pygame.Surface((32, 32), pygame.SRCALPHA)
    dead.draw(surface, pygame.Vector2(0.0, 0.0))


def test_inventory_rejects_invalid_item_add_and_missing_remove() -> None:
    inv = Inventory()
    inv.slots = [None for _ in range(27)]
    assert not inv.add_item(BLOCK_AIR, 1)
    assert not inv.add_item(BLOCK_DIRT, 0)
    assert not inv.remove_items(BLOCK_DIRT, 1)


def test_world_from_dict_handles_invalid_shapes() -> None:
    world = World.from_dict({"seed": 7, "chunks": {"0": [["bad"]], "1": "bad"}})
    assert world.seed == 7
    assert isinstance(world.chunks, dict)
