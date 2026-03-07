import random
import heapq
from .constants import *


# ============================================================
# DUNGEON GENERATION (BSP)
# ============================================================

class BSPNode:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.left = None
        self.right = None
        self.room = None

    def split(self, min_size=8, max_depth=5, depth=0):
        if depth >= max_depth:
            return
        if self.w < min_size * 2 and self.h < min_size * 2:
            return
        if self.w > self.h * 1.25:
            horizontal = False
        elif self.h > self.w * 1.25:
            horizontal = True
        else:
            horizontal = random.random() < 0.5
        if horizontal:
            if self.h < min_size * 2:
                return
            s = random.randint(min_size, self.h - min_size)
            self.left = BSPNode(self.x, self.y, self.w, s)
            self.right = BSPNode(self.x, self.y + s, self.w, self.h - s)
        else:
            if self.w < min_size * 2:
                return
            s = random.randint(min_size, self.w - min_size)
            self.left = BSPNode(self.x, self.y, s, self.h)
            self.right = BSPNode(self.x + s, self.y, self.w - s, self.h)
        self.left.split(min_size, max_depth, depth + 1)
        self.right.split(min_size, max_depth, depth + 1)

    def get_rooms(self):
        if self.room:
            return [self.room]
        rooms = []
        if self.left:
            rooms.extend(self.left.get_rooms())
        if self.right:
            rooms.extend(self.right.get_rooms())
        return rooms

    def create_rooms(self, tiles, min_room=4, padding=1):
        if self.left is None and self.right is None:
            rw = random.randint(min_room, max(min_room, self.w - padding * 2))
            rh = random.randint(min_room, max(min_room, self.h - padding * 2))
            rx = self.x + random.randint(padding, max(padding, self.w - rw - padding))
            ry = self.y + random.randint(padding, max(padding, self.h - rh - padding))
            rx = max(1, min(rx, MAP_W - rw - 1))
            ry = max(1, min(ry, MAP_H - rh - 1))
            rw = min(rw, MAP_W - rx - 1)
            rh = min(rh, MAP_H - ry - 1)
            if rw < min_room or rh < min_room:
                return
            self.room = (rx, ry, rw, rh)
            # Choose room shape variant
            shape = random.choices(
                ["rect", "circular", "l_shaped", "pillared"],
                weights=[50, 20, 15, 15], k=1)[0]
            _carve_room_shape(tiles, rx, ry, rw, rh, shape)
            return
        if self.left:
            self.left.create_rooms(tiles, min_room, padding)
        if self.right:
            self.right.create_rooms(tiles, min_room, padding)
        if self.left and self.right:
            lr = self.left.get_rooms()
            rr = self.right.get_rooms()
            if lr and rr:
                r1 = random.choice(lr)
                r2 = random.choice(rr)
                _carve_corridor(tiles, r1[0]+r1[2]//2, r1[1]+r1[3]//2,
                               r2[0]+r2[2]//2, r2[1]+r2[3]//2)


def _carve_room_shape(tiles, rx, ry, rw, rh, shape):
    """Carve a room of the given shape into the tile grid."""
    if shape == "rect":
        for yy in range(ry, ry + rh):
            for xx in range(rx, rx + rw):
                if 0 < xx < MAP_W - 1 and 0 < yy < MAP_H - 1:
                    tiles[yy][xx] = T_FLOOR
    elif shape == "circular":
        cx = rx + rw / 2.0
        cy = ry + rh / 2.0
        rx2 = rw / 2.0
        ry2 = rh / 2.0
        for yy in range(ry, ry + rh):
            for xx in range(rx, rx + rw):
                if 0 < xx < MAP_W - 1 and 0 < yy < MAP_H - 1:
                    dx = (xx + 0.5 - cx) / rx2
                    dy = (yy + 0.5 - cy) / ry2
                    if dx * dx + dy * dy <= 1.0:
                        tiles[yy][xx] = T_FLOOR
    elif shape == "l_shaped":
        # Carve an L-shape: full width top half, left half bottom half
        mid_y = ry + rh // 2
        mid_x = rx + rw // 2
        for yy in range(ry, ry + rh):
            for xx in range(rx, rx + rw):
                if 0 < xx < MAP_W - 1 and 0 < yy < MAP_H - 1:
                    if yy < mid_y or xx < mid_x:
                        tiles[yy][xx] = T_FLOOR
    elif shape == "pillared":
        # Rectangular room with interior pillars (wall tiles) for cover
        for yy in range(ry, ry + rh):
            for xx in range(rx, rx + rw):
                if 0 < xx < MAP_W - 1 and 0 < yy < MAP_H - 1:
                    tiles[yy][xx] = T_FLOOR
        # Place pillars every 2 tiles, inset by 1 from room edges
        for yy in range(ry + 1, ry + rh - 1, 2):
            for xx in range(rx + 1, rx + rw - 1, 2):
                if 0 < xx < MAP_W - 1 and 0 < yy < MAP_H - 1:
                    tiles[yy][xx] = T_WALL
    else:
        # Fallback: standard rect
        for yy in range(ry, ry + rh):
            for xx in range(rx, rx + rw):
                if 0 < xx < MAP_W - 1 and 0 < yy < MAP_H - 1:
                    tiles[yy][xx] = T_FLOOR


def _carve_corridor(tiles, x1, y1, x2, y2):
    x, y = x1, y1
    if random.random() < 0.5:
        while x != x2:
            if 0 < x < MAP_W-1 and 0 < y < MAP_H-1 and tiles[y][x] == T_WALL:
                tiles[y][x] = T_CORRIDOR
            x += 1 if x2 > x else -1
        while y != y2:
            if 0 < x < MAP_W-1 and 0 < y < MAP_H-1 and tiles[y][x] == T_WALL:
                tiles[y][x] = T_CORRIDOR
            y += 1 if y2 > y else -1
    else:
        while y != y2:
            if 0 < x < MAP_W-1 and 0 < y < MAP_H-1 and tiles[y][x] == T_WALL:
                tiles[y][x] = T_CORRIDOR
            y += 1 if y2 > y else -1
        while x != x2:
            if 0 < x < MAP_W-1 and 0 < y < MAP_H-1 and tiles[y][x] == T_WALL:
                tiles[y][x] = T_CORRIDOR
            x += 1 if x2 > x else -1
    if 0 < x2 < MAP_W-1 and 0 < y2 < MAP_H-1 and tiles[y2][x2] == T_WALL:
        tiles[y2][x2] = T_CORRIDOR


def flood_fill_count(tiles, sx, sy):
    visited = set()
    stack = [(sx, sy)]
    while stack:
        cx, cy = stack.pop()
        if (cx, cy) in visited:
            continue
        if cx < 0 or cx >= MAP_W or cy < 0 or cy >= MAP_H:
            continue
        if tiles[cy][cx] == T_WALL:
            continue
        visited.add((cx, cy))
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            stack.append((cx+dx, cy+dy))
    return len(visited)


def count_walkable(tiles):
    c = 0
    for row in tiles:
        for t in row:
            if t != T_WALL:
                c += 1
    return c


def generate_dungeon(floor_num, retries=20):
    for attempt in range(retries):
        tiles = [[T_WALL]*MAP_W for _ in range(MAP_H)]
        root = BSPNode(0, 0, MAP_W, MAP_H)
        depth = random.randint(3, 5)
        min_sz = random.randint(7, 10)
        root.split(min_size=min_sz, max_depth=depth)
        root.create_rooms(tiles, min_room=4, padding=1)
        rooms = root.get_rooms()
        if len(rooms) < 4:
            continue

        # Extra corridors for loops
        for _ in range(random.randint(1, 3)):
            r1 = random.choice(rooms)
            r2 = random.choice(rooms)
            if r1 != r2:
                _carve_corridor(tiles, r1[0]+r1[2]//2, r1[1]+r1[3]//2,
                               r2[0]+r2[2]//2, r2[1]+r2[3]//2)

        # Add some doors
        for y in range(1, MAP_H-1):
            for x in range(1, MAP_W-1):
                if tiles[y][x] == T_CORRIDOR:
                    h_choke = (tiles[y][x-1] == T_WALL and tiles[y][x+1] == T_WALL and
                               tiles[y-1][x] != T_WALL and tiles[y+1][x] != T_WALL)
                    v_choke = (tiles[y-1][x] == T_WALL and tiles[y+1][x] == T_WALL and
                               tiles[y][x-1] != T_WALL and tiles[y][x+1] != T_WALL)
                    if (h_choke or v_choke) and random.random() < 0.3:
                        tiles[y][x] = T_DOOR

        # Cave features for deeper floors
        if floor_num >= 4:
            _add_cave_features(tiles, floor_num)

        # Place stairs - maximize distance
        best_dist = 0
        start_room = rooms[0]
        end_room = rooms[-1]
        for i, r1 in enumerate(rooms):
            for j, r2 in enumerate(rooms):
                if i != j:
                    d = abs(r1[0]-r2[0]) + abs(r1[1]-r2[1])
                    if d > best_dist:
                        best_dist = d
                        start_room = r1
                        end_room = r2

        px = start_room[0] + start_room[2]//2
        py = start_room[1] + start_room[3]//2
        sx = end_room[0] + end_room[2]//2
        sy = end_room[1] + end_room[3]//2

        if floor_num < MAX_FLOORS:
            tiles[sy][sx] = T_STAIRS_DOWN
        if floor_num > 1:
            tiles[py][px] = T_STAIRS_UP

        # Verify connectivity
        walkable = count_walkable(tiles)
        reachable = flood_fill_count(tiles, px, py)
        if walkable > 0 and reachable >= walkable * 0.95:
            return tiles, rooms, (px, py), (sx, sy)

    return _generate_fallback(floor_num)


def _add_cave_features(tiles, floor_num):
    for _ in range(min(floor_num - 3, 4)):
        for _ in range(50):
            cx = random.randint(3, MAP_W-4)
            cy = random.randint(3, MAP_H-4)
            if tiles[cy][cx] != T_WALL:
                break
        else:
            continue
        x, y = cx, cy
        for _ in range(random.randint(10, 30)):
            dx, dy = random.choice([(-1,0),(1,0),(0,-1),(0,1)])
            x = max(1, min(MAP_W-2, x+dx))
            y = max(1, min(MAP_H-2, y+dy))
            if tiles[y][x] == T_WALL:
                tiles[y][x] = T_FLOOR

    if floor_num >= 7:
        for _ in range(random.randint(1, 3)):
            cx = random.randint(5, MAP_W-6)
            cy = random.randint(5, MAP_H-6)
            tile_t = T_LAVA if floor_num >= 10 else T_WATER
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    if abs(dx)+abs(dy) <= 2 and random.random() < 0.6:
                        nx, ny = cx+dx, cy+dy
                        if 0 < nx < MAP_W-1 and 0 < ny < MAP_H-1:
                            if tiles[ny][nx] == T_FLOOR:
                                tiles[ny][nx] = tile_t


def _generate_fallback(floor_num):
    tiles = [[T_WALL]*MAP_W for _ in range(MAP_H)]
    rooms = []
    for gy in range(3):
        for gx in range(4):
            rx = 3 + gx*18
            ry = 3 + gy*12
            rw = random.randint(5, 10)
            rh = random.randint(4, 7)
            if rx+rw < MAP_W-1 and ry+rh < MAP_H-1:
                rooms.append((rx, ry, rw, rh))
                for yy in range(ry, ry+rh):
                    for xx in range(rx, rx+rw):
                        tiles[yy][xx] = T_FLOOR
    for i in range(len(rooms)-1):
        r1, r2 = rooms[i], rooms[i+1]
        _carve_corridor(tiles, r1[0]+r1[2]//2, r1[1]+r1[3]//2,
                       r2[0]+r2[2]//2, r2[1]+r2[3]//2)
    px = rooms[0][0]+rooms[0][2]//2
    py = rooms[0][1]+rooms[0][3]//2
    sx = rooms[-1][0]+rooms[-1][2]//2
    sy = rooms[-1][1]+rooms[-1][3]//2
    if floor_num < MAX_FLOORS:
        tiles[sy][sx] = T_STAIRS_DOWN
    if floor_num > 1:
        tiles[py][px] = T_STAIRS_UP
    return tiles, rooms, (px, py), (sx, sy)


# ============================================================
# FOV (Recursive Shadowcasting)
# ============================================================

_MULT = [
    [1,  0,  0, -1, -1,  0,  0,  1],
    [0,  1, -1,  0,  0, -1,  1,  0],
    [0,  1,  1,  0,  0, -1, -1,  0],
    [1,  0,  0,  1, -1,  0,  0, -1],
]

def compute_fov(tiles, px, py, radius, visible_set):
    """Compute field of view using recursive shadowcasting for 8 octants."""
    visible_set.clear()
    visible_set.add((px, py))
    for octant in range(8):
        _cast_light(tiles, px, py, radius, 1, 1.0, 0.0, octant, visible_set)

def _cast_light(tiles, cx, cy, radius, row, start, end, octant, visible):
    if start < end:
        return
    radius_sq = radius * radius
    for j in range(row, radius+1):
        dx = -j - 1
        dy = -j
        blocked = False
        new_start = start
        while dx <= 0:
            dx += 1
            mx = cx + dx*_MULT[0][octant] + dy*_MULT[1][octant]
            my = cy + dx*_MULT[2][octant] + dy*_MULT[3][octant]
            l_slope = (dx - 0.5) / (dy + 0.5)
            r_slope = (dx + 0.5) / (dy - 0.5)
            if start < r_slope:
                continue
            elif end > l_slope:
                break
            if dx*dx + dy*dy <= radius_sq:
                if 0 <= mx < MAP_W and 0 <= my < MAP_H:
                    visible.add((mx, my))
            if blocked:
                if 0 <= mx < MAP_W and 0 <= my < MAP_H and tiles[my][mx] == T_WALL:
                    new_start = r_slope
                    continue
                else:
                    blocked = False
                    start = new_start
            else:
                if 0 <= mx < MAP_W and 0 <= my < MAP_H and tiles[my][mx] == T_WALL and j < radius:
                    blocked = True
                    _cast_light(tiles, cx, cy, radius, j+1, start, l_slope, octant, visible)
                    new_start = r_slope
        if blocked:
            break


# ============================================================
# PATHFINDING
# ============================================================

def astar(tiles, sx, sy, gx, gy, max_steps=20):
    """A* pathfinding from (sx,sy) to (gx,gy). Returns (dx,dy) for first step or None."""
    if sx == gx and sy == gy:
        return (0, 0)
    open_set = [(0, sx, sy)]
    came_from = {}
    g_score = {(sx, sy): 0}
    closed = set()
    while open_set:
        _, cx, cy = heapq.heappop(open_set)
        if (cx, cy) in closed:
            continue
        closed.add((cx, cy))
        if cx == gx and cy == gy:
            path = []
            pos = (gx, gy)
            while pos in came_from:
                path.append(pos)
                pos = came_from[pos]
            if path:
                nx, ny = path[-1]
                return (nx - sx, ny - sy)
            return None
        for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx, ny = cx+ddx, cy+ddy
            if nx < 0 or nx >= MAP_W or ny < 0 or ny >= MAP_H:
                continue
            if tiles[ny][nx] == T_WALL or tiles[ny][nx] == T_LAVA:
                continue
            ng = g_score[(cx,cy)] + 1
            if ng > max_steps:
                continue
            if (nx,ny) not in g_score or ng < g_score[(nx,ny)]:
                g_score[(nx,ny)] = ng
                f = ng + abs(nx-gx) + abs(ny-gy)
                came_from[(nx,ny)] = (cx,cy)
                heapq.heappush(open_set, (f, nx, ny))
    return None


def _has_los(tiles, x1, y1, x2, y2):
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    sx = 1 if x2 > x1 else -1
    sy = 1 if y2 > y1 else -1
    err = dx - dy
    x, y = x1, y1
    while True:
        if x == x2 and y == y2:
            return True
        if 0 <= y < MAP_H and 0 <= x < MAP_W and tiles[y][x] == T_WALL:
            return False
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy
