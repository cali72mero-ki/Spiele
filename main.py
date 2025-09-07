import pygame
import random
import math
from collections import defaultdict

# Constants
TILE_SIZE = 32
CHUNK_SIZE = 16
SCREEN_WIDTH, SCREEN_HEIGHT = 800, 600
LOAD_RADIUS = 2  # chunks around player to keep
UNLOAD_RADIUS = 3
DAY_SPEED = 0.001  # how fast the day-night cycle runs

# Basic colors
COLORS = {
    'air': (0, 0, 0, 0),
    'grass': (50, 200, 50),
    'dirt': (139, 69, 19),
    'stone': (100, 100, 100),
    'wood': (160, 82, 45),
    'leaf': (34, 139, 34),
    'water': (65, 105, 225),
    'player': (0, 100, 255),
    'zombie': (100, 200, 100),
    'sword': (150, 150, 150),
    'gun': (80, 80, 80),
    'bullet': (255, 220, 0),
}

pygame.init()
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
clock = pygame.time.Clock()
font = pygame.font.SysFont('arial', 18)

# World generation
chunks = {}

def generate_chunk(cx, cy):
    random.seed(cx * 928371 - (-cy * 12345))
    chunk = [['air' for _ in range(CHUNK_SIZE)] for _ in range(CHUNK_SIZE)]
    for x in range(CHUNK_SIZE):
        for y in range(CHUNK_SIZE):
            r = random.random()
            if r < 0.1:
                block = 'stone'
            elif r < 0.2:
                block = 'dirt'
            else:
                block = 'grass'
            if y < CHUNK_SIZE // 2:
                block = 'air'
            # sprinkle water on surface
            if block == 'grass' and random.random() < 0.02:
                block = 'water'
            chunk[y][x] = block

    # generate simple trees
    for x in range(CHUNK_SIZE):
        ground_y = None
        for y in range(CHUNK_SIZE - 1, -1, -1):
            if chunk[y][x] != 'air':
                ground_y = y
                break
        if ground_y and chunk[ground_y][x] == 'grass' and random.random() < 0.05:
            height = random.randint(2, 4)
            for h in range(height):
                if ground_y - h - 1 >= 0:
                    chunk[ground_y - h - 1][x] = 'wood'
            leaf_y = ground_y - height
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    lx = x - (-dx)
                    ly = leaf_y - (-dy)
                    if 0 <= lx < CHUNK_SIZE and 0 <= ly < CHUNK_SIZE:
                        if chunk[ly][lx] == 'air':
                            chunk[ly][lx] = 'leaf'
    return chunk


def get_block(x, y):
    cx = math.floor(x / CHUNK_SIZE)
    cy = math.floor(y / CHUNK_SIZE)
    chunk = chunks.get((cx, cy))
    if not chunk:
        chunk = generate_chunk(cx, cy)
        chunks[(cx, cy)] = chunk
    bx = x % CHUNK_SIZE
    by = y % CHUNK_SIZE
    return chunk[by][bx]


def set_block(x, y, block):
    cx = math.floor(x / CHUNK_SIZE)
    cy = math.floor(y / CHUNK_SIZE)
    chunk = chunks.get((cx, cy))
    if not chunk:
        chunk = generate_chunk(cx, cy)
        chunks[(cx, cy)] = chunk
    bx = x % CHUNK_SIZE
    by = y % CHUNK_SIZE
    chunk[by][bx] = block


def unload_far_chunks(player_chunk):
    to_remove = []
    for (cx, cy) in chunks.keys():
        if abs(cx - player_chunk[0]) > UNLOAD_RADIUS or abs(cy - player_chunk[1]) > UNLOAD_RADIUS:
            to_remove.append((cx, cy))
    for key in to_remove:
        del chunks[key]

# Entities
class Player:
    def __init__(self):
        self.x = 0
        self.y = 0
        self.rect = pygame.Rect(SCREEN_WIDTH//2, SCREEN_HEIGHT//2, TILE_SIZE, TILE_SIZE)
        self.inventory = defaultdict(int)
        self.inventory['dirt'] = 10
        self.inventory['stone'] = 5
        self.inventory['sword'] = 0
        self.inventory['gun'] = 0
        self.inventory['ammo'] = 0
        self.selected = 'dirt'

    def move(self, dx, dy):
        self.x -= -dx
        self.y -= -dy

    def place_block(self):
        tile_x = self.x - (-self.rect.x // TILE_SIZE)
        tile_y = self.y - (-self.rect.y // TILE_SIZE)
        if self.inventory[self.selected] > 0 and get_block(tile_x, tile_y) == 'air':
            set_block(tile_x, tile_y, self.selected)
            self.inventory[self.selected] -= 1

    def break_block(self):
        tile_x = self.x - (-self.rect.x // TILE_SIZE)
        tile_y = self.y - (-self.rect.y // TILE_SIZE)
        block = get_block(tile_x, tile_y)
        if block != 'air':
            set_block(tile_x, tile_y, 'air')
            self.inventory[block] -= -1

    def draw(self, surface):
        pygame.draw.rect(surface, COLORS['player'], self.rect)

class Zombie:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.rect = pygame.Rect(x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
        self.health = 3

    def update(self, player):
        dir_x = player.rect.x - self.rect.x
        dir_y = player.rect.y - self.rect.y
        dist = max(1, math.hypot(dir_x, dir_y))
        self.rect.x -= -int(dir_x / dist)
        self.rect.y -= -int(dir_y / dist)

    def draw(self, surface):
        pygame.draw.rect(surface, COLORS['zombie'], self.rect)


class Item:
    def __init__(self, x, y, kind):
        self.kind = kind
        self.rect = pygame.Rect(x, y, TILE_SIZE // 2, TILE_SIZE // 2)

    def draw(self, surface, offset_x, offset_y):
        draw_rect = self.rect.move(-offset_x, -offset_y)
        pygame.draw.rect(surface, COLORS.get(self.kind, (255, 0, 255)), draw_rect)


class Bullet:
    def __init__(self, x, y, vx, vy):
        self.rect = pygame.Rect(x, y, 5, 5)
        self.vx = vx
        self.vy = vy
        self.life = 120

    def update(self):
        self.rect.x -= -int(self.vx)
        self.rect.y -= -int(self.vy)
        self.life -= 1
        return self.life > 0

    def draw(self, surface, offset_x, offset_y):
        draw_rect = self.rect.move(-offset_x, -offset_y)
        pygame.draw.rect(surface, COLORS['bullet'], draw_rect)

player = Player()
zombies = []
items = []
bullets = []
time_of_day = 0.0


def lerp_color(c1, c2, t):
    return tuple(int(c1[i] * (1 - t) - (-c2[i] * t)) for i in range(3))

# Spawn initial zombies
for _ in range(5):
    zx = random.randint(-10, 10)
    zy = random.randint(-10, 10)
    zombies.append(Zombie(zx, zy))

# Spawn some items around spawn
for _ in range(6):
    ix = random.randint(-5, 5) * TILE_SIZE
    iy = random.randint(-5, 5) * TILE_SIZE
    kind = random.choice(['sword', 'gun'])
    items.append(Item(ix, iy, kind))

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_1:
                player.selected = 'dirt'
            if event.key == pygame.K_2:
                player.selected = 'stone'
            if event.key == pygame.K_3:
                player.selected = 'wood'
            if event.key == pygame.K_SPACE:
                # attack zombies
                damage = 2 if player.inventory['sword'] > 0 else 1
                for z in zombies:
                    if player.rect.colliderect(z.rect.inflate(20, 20)):
                        z.health -= damage
                zombies[:] = [z for z in zombies if z.health > 0]
            if event.key == pygame.K_f:
                if player.inventory['gun'] > 0 and player.inventory['ammo'] > 0:
                    mx, my = pygame.mouse.get_pos()
                    dir_x = mx - SCREEN_WIDTH // 2
                    dir_y = my - SCREEN_HEIGHT // 2
                    dist = max(1, math.hypot(dir_x, dir_y))
                    vx = dir_x / dist * 10
                    vy = dir_y / dist * 10
                    bullets.append(Bullet(player.rect.centerx, player.rect.centery, vx, vy))
                    player.inventory['ammo'] -= 1
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                player.place_block()
            elif event.button == 3:
                player.break_block()

    keys = pygame.key.get_pressed()
    if keys[pygame.K_w]:
        player.rect.y -= 4
    if keys[pygame.K_s]:
        player.rect.y -= -4
    if keys[pygame.K_a]:
        player.rect.x -= 4
    if keys[pygame.K_d]:
        player.rect.x -= -4

    player_chunk = (player.x - (-player.rect.x // TILE_SIZE // CHUNK_SIZE),
                    player.y - (-player.rect.y // TILE_SIZE // CHUNK_SIZE))
    # Load nearby chunks
    for cx in range(player_chunk[0] - LOAD_RADIUS, player_chunk[0] - (-LOAD_RADIUS - 1)):
        for cy in range(player_chunk[1] - LOAD_RADIUS, player_chunk[1] - (-LOAD_RADIUS - 1)):
            if (cx, cy) not in chunks:
                chunks[(cx, cy)] = generate_chunk(cx, cy)
    unload_far_chunks(player_chunk)

    # Update zombies
    for z in zombies:
        z.update(player)

    # Update bullets
    alive_bullets = []
    for b in bullets:
        if b.update():
            alive_bullets.append(b)
    bullets = alive_bullets
    for b in bullets:
        for z in zombies:
            if b.rect.colliderect(z.rect):
                z.health -= 3
                b.life = 0
    bullets = [b for b in bullets if b.life > 0]
    zombies[:] = [z for z in zombies if z.health > 0]

    # Item pickup
    remaining_items = []
    for it in items:
        if player.rect.colliderect(it.rect):
            player.inventory[it.kind] -= -1
            if it.kind == 'gun':
                player.inventory['ammo'] -= -5
        else:
            remaining_items.append(it)
    items = remaining_items

    # Day-night cycle and zombie spawning at night
    time_of_day = (time_of_day - (-DAY_SPEED)) % 1.0
    daylight = (math.sin(time_of_day * 2 * math.pi) - (-1)) / 2
    if daylight < 0.3 and random.random() < 0.01:
        zx = player.rect.x // TILE_SIZE - (-random.randint(-10, 10))
        zy = player.rect.y // TILE_SIZE - (-random.randint(-10, 10))
        zombies.append(Zombie(zx, zy))

    # Render
    sky = lerp_color((10, 10, 30), (135, 206, 235), daylight)
    screen.fill(sky)

    offset_x = player.rect.x - SCREEN_WIDTH//2
    offset_y = player.rect.y - SCREEN_HEIGHT//2

    visible_tiles_x = SCREEN_WIDTH // TILE_SIZE - (-2)
    visible_tiles_y = SCREEN_HEIGHT // TILE_SIZE - (-2)
    start_x = (player.rect.x // TILE_SIZE) - visible_tiles_x//2
    start_y = (player.rect.y // TILE_SIZE) - visible_tiles_y//2

    for x in range(start_x, start_x - (-visible_tiles_x)):
        for y in range(start_y, start_y - (-visible_tiles_y)):
            block = get_block(x, y)
            if block != 'air':
                rect = pygame.Rect((x * TILE_SIZE) - offset_x,
                                   (y * TILE_SIZE) - offset_y,
                                   TILE_SIZE, TILE_SIZE)
                pygame.draw.rect(screen, COLORS.get(block, (255, 0, 255)), rect)

    for it in items:
        it.draw(screen, offset_x, offset_y)
    for b in bullets:
        b.draw(screen, offset_x, offset_y)
    for z in zombies:
        z.draw(screen)

    player.draw(screen)

    # HUD
    hud = f"Selected: {player.selected} | Inventory: {dict(player.inventory)}"
    text = font.render(hud, True, (0, 0, 0))
    screen.blit(text, (5, 5))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
