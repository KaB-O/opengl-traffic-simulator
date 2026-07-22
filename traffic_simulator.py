"""
=============================================================================
MEMBER 1 GAME - AUTONOMOUS CITY TRAFFIC SIMULATOR
=============================================================================
Combining Member1.py controls with 2.py city environment

Features Implemented:
1. Automatic route selection for vehicles
2. Collision detection and avoidance
3. Weather effects (rain/fog) on speed and safety
4. Speed control based on traffic density
5. Driving seat view (First Person)
6. Aerial view with car selection for simulation
7. Red-light violation detection
8. Start / Pause / Reset simulation

Controls:
- 1-4: Select car color at start screen
- Arrow Keys: Steer left/right
- Page Up/Down: Accelerate/Decelerate
- V: Toggle view (TOP / DRIVER / FIRST_PERSON)
- E: Cycle through vehicles (in DRIVER mode)
- Enter: Toggle engine on/off
- Space: Pause/Resume simulation
- R: Toggle rain
- F: Toggle fog
- X: Reset simulation
=============================================================================
"""

import math
import random
import sys
import time

from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GLUT import *

# =============================================================================
# CONFIGURATION
# =============================================================================

WINDOW_W, WINDOW_H = 1000, 800
TILE_SIZE = 80  # Tile size for roads
ROAD_WIDTH = 40  # Wider roads for better car control
LANE_OFFSET = 18  # Lane offset for right-hand traffic (increased for proper separation)
BLOCK_SIZE = 5  # Number of tiles per block (creates longer roads between intersections)
NUM_BLOCKS = 8  # 8x8 blocks
MAP_SIZE = NUM_BLOCKS * BLOCK_SIZE + 1  # Total map size in tiles (41x41 for 8x8 blocks)
SPEED_LIMIT = 3.0
OVERSPEEDING_CRASH_CHANCE = 0.03

# Day/Night cycle
CYCLE_DURATION = 30.0  # seconds for full day/night cycle

# Pedestrian settings
MAX_PEDESTRIANS = 12

# Pothole settings
POTHOLE_COVERAGE_RATE = 0.005  # 0.5% of road tiles will have potholes

# Violator rate (NPCs that ignore signals)
VIOLATOR_RATE = 0.05  # 5%

# AI Overspeeding rate - these AI cars will overspeed and may cause accidents
AI_OVERSPEEDING_RATE = 0.02  # 2%

# Random accident settings
RANDOM_ACCIDENT_COOLDOWN = 100.0  # seconds between random accidents
RANDOM_ACCIDENT_BASE_CHANCE = 0.0000035

# Life system settings
LIFE_LOSS_COOLDOWN = 3.0  # seconds between life losses

# Footpath settings
FOOTPATH_WIDTH = 8  # Width of sidewalk along roads

# =============================================================================
# MAP GENERATOR
# =============================================================================


def generate_city_map(size):
    """Generate an 8x8 block city map with grid roads"""
    layout = [[0 for _ in range(size)] for _ in range(size)]
    for r in range(size):
        for c in range(size):
            # Create grid roads every BLOCK_SIZE tiles (creates 8x8 blocks)
            # Roads are placed at regular intervals to form a grid
            if r % BLOCK_SIZE == 0 or c % BLOCK_SIZE == 0:
                layout[r][c] = 1
    return layout


def is_position_on_road(x, y):
    """Check if a world position is on a road"""
    row, col = get_tile_coords(x, y)
    if 0 <= row < len(CITY_LAYOUT) and 0 <= col < len(CITY_LAYOUT[0]):
        return CITY_LAYOUT[row][col] == 1
    return False


def get_nearest_road_position(x, y):
    """Find the nearest valid road position from current position"""
    current_row, current_col = get_tile_coords(x, y)

    # Search in expanding circles for nearest road
    for radius in range(1, max(MAP_SIZE, MAP_SIZE)):
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                check_row = current_row + dr
                check_col = current_col + dc
                if 0 <= check_row < len(CITY_LAYOUT) and 0 <= check_col < len(
                    CITY_LAYOUT[0]
                ):
                    if CITY_LAYOUT[check_row][check_col] == 1:
                        # Return center of this road tile
                        return (
                            check_col * TILE_SIZE + TILE_SIZE / 2,
                            check_row * TILE_SIZE + TILE_SIZE / 2,
                        )
    return x, y  # Fallback to current position


CITY_LAYOUT = generate_city_map(MAP_SIZE)

# =============================================================================
# GLOBAL STATE
# =============================================================================

# Simulation state
sim_running = True
game_state = "START_SCREEN"
start_time = time.time()

# Player state
player_lives = 20  # Increased from 5
has_deducted_life = False
violation_detected = False
selected_car_color = 0
selection_colors = [[1, 0.2, 0.2], [0.2, 0.3, 1], [1, 1, 0.2], [1, 1, 1]]

# Life system (from member3)
last_life_loss_time = 0.0
player_crashed = False  # Crash lock to prevent repeated deductions

# Day/Night cycle
is_night = False

# Key hold states for smooth acceleration
key_accel = False
key_brake = False

# Random accident timing
last_random_accident_time = 0.0

# View state
view_mode = "TOP"  # TOP, THIRD_PERSON, FIRST_PERSON
selected_vehicle_index = 0

# Camera settings for different views
CAMERA_SETTINGS = {
    "TOP": {
        "height": 3500,  # High enough to see full 8x8 city
    },
    "THIRD_PERSON": {
        "height": 18,  # Just above the car - closer view
        "distance": 35,  # Close behind the car - much closer
        "look_ahead": 50,  # Look slightly ahead
        "look_height": 8,  # See slightly above ground
    },
    "FIRST_PERSON": {
        "height": 20,  # Hood/dashboard level for racing view
        "forward_offset": 25,  # In front of car (on the hood)
        "look_ahead": 400,  # Look far down the road
        "look_height": 12,  # See the road ahead
    },
}

# Player highlight settings
PLAYER_HIGHLIGHT_COLOR = [0, 1, 0]  # Green highlight ring
PLAYER_HIGHLIGHT_PULSE_SPEED = 4.0

# Weather state
weather_raining = False
weather_fog = False
rain_particles = []
MAX_RAIN = 400

# Simulation data
vehicles = []
traffic_lights = []
accidents = []
alert_messages = []
road_blocks = []  # Road block positions
pedestrians = []  # Pedestrian list
potholes = []  # Pothole list

# Emergency vehicle spawning
EMERGENCY_SPAWN_CHANCE = 0.10  # 10% chance
EMERGENCY_SPAWN_INTERVAL = 30.0  # Every 30 seconds

# Collision settings
VEHICLE_COLLISION_RADIUS = 18.0  # Distance for collision detection
last_emergency_spawn_time = 0

# Timing
last_frame_time = time.time()
time_diff = 0.016

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_tile_coords(x, y):
    """Convert world coordinates to tile coordinates"""
    col = int(x / TILE_SIZE)
    row = int(y / TILE_SIZE)
    return row, col


def is_road(row, col):
    """Check if a tile is a road"""
    if 0 <= row < len(CITY_LAYOUT) and 0 <= col < len(CITY_LAYOUT[0]):
        return CITY_LAYOUT[row][col] == 1
    return False


def is_footpath_position(x, y):
    """Check if a world position is on a footpath (sidewalk adjacent to road)"""
    row, col = get_tile_coords(x, y)

    # Must not be on a road
    if is_road(row, col):
        return False

    # Must be adjacent to a road (at least one neighboring tile is a road)
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        if is_road(row + dr, col + dc):
            # Check if we're within footpath distance from the road edge
            tile_x = col * TILE_SIZE + TILE_SIZE / 2
            tile_y = row * TILE_SIZE + TILE_SIZE / 2

            # Distance from tile center
            dist_from_center = math.sqrt((x - tile_x)**2 + (y - tile_y)**2)

            # Footpath is the outer edge of the building tile adjacent to road
            # Only the part closest to the road
            if dist_from_center < TILE_SIZE * 0.6:  # Within the tile's footpath area
                return True

    return False


def get_footpath_positions_near(x, y, radius=300):
    """Get valid footpath positions near a location"""
    positions = []

    start_col = max(0, int((x - radius) / TILE_SIZE))
    end_col = min(len(CITY_LAYOUT[0]) - 1, int((x + radius) / TILE_SIZE))
    start_row = max(0, int((y - radius) / TILE_SIZE))
    end_row = min(len(CITY_LAYOUT) - 1, int((y + radius) / TILE_SIZE))

    for row in range(start_row, end_row + 1):
        for col in range(start_col, end_col + 1):
            # Skip road tiles
            if is_road(row, col):
                continue

            # Check if adjacent to road
            adjacent_to_road = False
            road_direction = None
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                if is_road(row + dr, col + dc):
                    adjacent_to_road = True
                    road_direction = (dr, dc)
                    break

            if adjacent_to_road and road_direction:
                # Place footpath position on the edge closest to the road
                tile_center_x = col * TILE_SIZE + TILE_SIZE / 2
                tile_center_y = row * TILE_SIZE + TILE_SIZE / 2

                # Offset towards the road
                dr, dc = road_direction
                fp_x = tile_center_x + dc * (TILE_SIZE / 2 - FOOTPATH_WIDTH)
                fp_y = tile_center_y + dr * (TILE_SIZE / 2 - FOOTPATH_WIDTH)

                positions.append((fp_x, fp_y))

    return positions


def get_available_directions(row, col, current_angle):
    """Get available turn directions at an intersection"""
    dir_map = {0: (0, 1), 90: (1, 0), 180: (0, -1), 270: (-1, 0)}
    directions = []
    for angle, (dr, dc) in dir_map.items():
        if is_road(row + dr, col + dc):
            directions.append(angle)

    # Don't go backward unless it's the only option
    backward = (current_angle + 180) % 360
    if len(directions) > 1 and backward in directions:
        directions.remove(backward)
    return directions


def add_alert(message):
    """Add an alert message to display"""
    global alert_messages
    alert_messages.append((message, time.time()))
    print(f"[ALERT] {message}")
    if len(alert_messages) > 5:
        alert_messages = alert_messages[-5:]


def lose_life(reason=""):
    """Handle life loss with cooldown (from member3)"""
    global player_lives, game_state, last_life_loss_time, player_crashed
    now = time.time()
    if now - last_life_loss_time < LIFE_LOSS_COOLDOWN:
        return False

    player_lives -= 1
    last_life_loss_time = now
    player_crashed = True
    add_alert(f"LIFE LOST: {reason} (Lives: {player_lives}) - Press T to respawn")

    if player_lives <= 0:
        game_state = "START_SCREEN"
        add_alert("GAME OVER!")
        return True
    return True


def clear_accident_and_resume():
    """Clear accidents and allow player to continue (from member3)"""
    global player_crashed, accidents, road_blocks

    if not vehicles:
        return

    v = vehicles[0]
    v.speed = 0
    v.target_speed = 0
    v.crashed = False

    # Clear nearby accidents and road blocks
    player_x, player_y = v.x, v.y
    accidents[:] = [a for a in accidents if math.sqrt((a['x'] - player_x)**2 + (a['y'] - player_y)**2) > 150]
    road_blocks[:] = [b for b in road_blocks if math.sqrt((b['x'] - player_x)**2 + (b['y'] - player_y)**2) > 150]

    player_crashed = False
    add_alert("ACCIDENT CLEARED - CONTINUE DRIVING")


# =============================================================================
# PEDESTRIAN CLASS (from member3)
# =============================================================================


class Pedestrian:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.z = 3.0
        self.speed = random.uniform(0.25, 0.5)  # Slower walking speed
        self.direction = random.uniform(0, 2 * math.pi)
        self.crossing = False
        self.radius = 6.0
        self.next_change = time.time() + random.uniform(2.5, 6.0)
        self.last_valid_x = x
        self.last_valid_y = y

    def update(self):
        """Update pedestrian movement - stay on footpaths"""
        avoid_x, avoid_y = 0.0, 0.0
        avoid_count = 0

        # Avoid accidents
        for a in accidents:
            dx = self.x - a['x']
            dy = self.y - a['y']
            dist_sq = dx*dx + dy*dy
            if dist_sq < (80.0)**2:
                avoid_x += dx
                avoid_y += dy
                avoid_count += 1

        # Avoid road blocks
        for b in road_blocks:
            dx = self.x - b['x']
            dy = self.y - b['y']
            dist_sq = dx*dx + dy*dy
            if dist_sq < (60.0)**2:
                avoid_x += dx
                avoid_y += dy
                avoid_count += 1

        # Avoid potholes
        for h in potholes:
            dx = self.x - h.x
            dy = self.y - h.y
            dist_sq = dx*dx + dy*dy
            if dist_sq < (h.radius + 30.0)**2:
                avoid_x += dx
                avoid_y += dy
                avoid_count += 1

        # Avoid vehicles on road
        for v in vehicles:
            dx = self.x - v.x
            dy = self.y - v.y
            dist_sq = dx*dx + dy*dy
            if dist_sq < (50.0)**2:
                avoid_x += dx
                avoid_y += dy
                avoid_count += 1

        now = time.time()
        if now > self.next_change:
            self.next_change = now + random.uniform(3.0, 8.0)
            # Occasionally cross the road at intersections
            self.crossing = (random.random() < 0.15)  # Less frequent crossing
            # Change to a random direction along footpath
            self.direction = random.choice([0, math.pi/2, math.pi, 3*math.pi/2]) + random.uniform(-0.3, 0.3)

        if avoid_count > 0:
            self.direction = math.atan2(avoid_y, avoid_x)

        # Calculate new position
        new_x = self.x + math.cos(self.direction) * self.speed
        new_y = self.y + math.sin(self.direction) * self.speed

        # Keep within map bounds
        limit = len(CITY_LAYOUT) * TILE_SIZE
        new_x = max(TILE_SIZE, min(limit - TILE_SIZE, new_x))
        new_y = max(TILE_SIZE, min(limit - TILE_SIZE, new_y))

        # Only move if staying on footpath (or crossing road at intersection)
        row, col = get_tile_coords(new_x, new_y)
        on_road = is_road(row, col)
        on_footpath = is_footpath_position(new_x, new_y)

        if on_footpath:
            # Valid footpath position
            self.x = new_x
            self.y = new_y
            self.last_valid_x = new_x
            self.last_valid_y = new_y
        elif on_road and self.crossing:
            # Allow crossing road briefly
            self.x = new_x
            self.y = new_y
        else:
            # Invalid position - change direction and stay put
            self.direction = random.uniform(0, 2 * math.pi)
            # Snap back to last valid position if too far from footpath
            if not is_footpath_position(self.x, self.y) and not (is_road(row, col) and self.crossing):
                self.x = self.last_valid_x
                self.y = self.last_valid_y

    def draw(self):
        """Draw pedestrian as a simple person shape"""
        glPushMatrix()
        glTranslatef(self.x, self.y, 0)
        glDisable(GL_LIGHTING)

        # Body (cylinder approximation)
        glColor3f(0.2, 0.4, 0.8)  # Blue clothes
        glPushMatrix()
        glTranslatef(0, 0, 4)
        glScalef(3, 3, 6)
        glutSolidCube(1)
        glPopMatrix()

        # Head
        glColor3f(1.0, 0.85, 0.7)  # Skin tone
        glPushMatrix()
        glTranslatef(0, 0, 9)
        glutSolidSphere(2.5, 8, 8)
        glPopMatrix()

        glEnable(GL_LIGHTING)
        glPopMatrix()


# =============================================================================
# POTHOLE CLASS (from member3)
# =============================================================================


class Pothole:
    def __init__(self, x, y, radius=12.0):  # Smaller default radius
        self.x = x
        self.y = y
        self.radius = radius

    def contains(self, px, py):
        dx = px - self.x
        dy = py - self.y
        return (dx * dx + dy * dy) <= (self.radius * self.radius)

    def draw(self):
        glPushMatrix()
        glTranslatef(self.x, self.y, 1.0)
        glDisable(GL_LIGHTING)
        glColor3f(0.05, 0.05, 0.05)  # Dark black pothole
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(0, 0, 0)
        steps = 28
        for i in range(steps + 1):
            a = (2 * math.pi * i) / steps
            glVertex3f(math.cos(a) * self.radius, math.sin(a) * self.radius, 0)
        glEnd()
        glEnable(GL_LIGHTING)
        glPopMatrix()


def draw_text(x, y, text, font=GLUT_BITMAP_HELVETICA_18):
    """Draw 2D text on screen"""
    glRasterPos2f(x, y)
    for char in text:
        glutBitmapCharacter(font, ord(char))


# =============================================================================
# TRAFFIC LIGHT SYSTEM - REALISTIC INTERSECTION CONTROL
# =============================================================================


class IntersectionController:
    """
    Controls traffic lights at a single intersection.
    Ensures that only one direction (NS or EW) has green at a time.
    Follows real-world convention: when one direction is green, the other is red.
    """

    def __init__(self, x, y, intersection_id):
        self.x = x
        self.y = y
        self.intersection_id = intersection_id

        # Traffic light states: "NS_GREEN" or "EW_GREEN"
        # NS = North-South (vertical road), EW = East-West (horizontal road)
        # Initial phase will be set based on intersection position for realistic coordination
        self.current_phase = "NS_GREEN"  # Default, will be overridden
        self.timer = time.time()

        # Timing settings - realistic timings
        self.green_duration = 8.0  # Base green time (longer for realism)
        self.yellow_duration = 3.0  # Yellow transition time
        self.all_red_duration = 1.0  # All-red clearance interval
        self.min_green = 3.0  # Reduced for no traffic
        self.max_green = 18.0  # Extended for heavy traffic

        # Current state in cycle: "GREEN", "YELLOW", "RED"
        self.ns_state = "GREEN"
        self.ew_state = "RED"

        # Vehicle counts per direction
        self.ns_vehicle_count = 0
        self.ew_vehicle_count = 0

        # Yellow transition tracking
        self.in_yellow_transition = False
        self.yellow_start_time = 0

        # All-red phase tracking (safety clearance)
        self.in_all_red = False
        self.all_red_start_time = 0

        # Emergency vehicle priority
        self.emergency_override = False
        self.emergency_override_direction = None  # "NS" or "EW"
        self.emergency_override_start = 0
        self.emergency_override_duration = 5.0  # 5 seconds override

    def count_vehicles_by_direction(self, all_vehicles):
        """Count vehicles approaching from each direction"""
        self.ns_vehicle_count = 0
        self.ew_vehicle_count = 0

        for v in all_vehicles:
            if v.crashed:
                continue
            dist = math.sqrt((v.x - self.x) ** 2 + (v.y - self.y) ** 2)
            if dist < 150:
                # Check vehicle direction
                angle_norm = v.angle % 360
                if angle_norm in [90, 270]:  # North or South
                    self.ns_vehicle_count += 1
                elif angle_norm in [0, 180]:  # East or West
                    self.ew_vehicle_count += 1

    def get_adaptive_green_time(self, vehicle_count):
        """Calculate green time based on traffic density"""
        if vehicle_count >= 10:  # Heavy traffic - maximum extension
            return self.max_green + 10.0  # Extra 10 seconds for heavy traffic
        elif vehicle_count >= 6:  # Medium-heavy traffic
            return self.max_green
        elif vehicle_count >= 3:  # Light-medium traffic
            return self.green_duration + 3.0
        elif vehicle_count > 0:  # Light traffic
            return self.green_duration
        else:  # No vehicles - minimum green
            return self.min_green

    def trigger_emergency_override(self, direction):
        """Trigger emergency vehicle priority - immediately switch lights"""
        if not self.emergency_override:
            self.emergency_override = True
            self.emergency_override_direction = direction
            self.emergency_override_start = time.time()

            # Immediately set the light for emergency direction to green
            if direction == "NS":
                self.ns_state = "GREEN"
                self.ew_state = "RED"
                self.current_phase = "NS_GREEN"
            else:  # EW
                self.ns_state = "RED"
                self.ew_state = "GREEN"
                self.current_phase = "EW_GREEN"

            # Cancel any transitions
            self.in_yellow_transition = False
            self.in_all_red = False
            self.timer = time.time()

    def update(self, all_vehicles):
        """Update traffic light states with realistic timing including all-red clearance"""
        self.count_vehicles_by_direction(all_vehicles)
        current_time = time.time()
        elapsed = current_time - self.timer

        # Check for emergency vehicles approaching
        for v in all_vehicles:
            if hasattr(v, 'is_emergency') and v.is_emergency and not v.crashed:
                dist = math.sqrt((v.x - self.x) ** 2 + (v.y - self.y) ** 2)
                if dist < 200:  # Emergency vehicle approaching
                    angle_norm = v.angle % 360
                    if angle_norm in [90, 270]:  # NS direction
                        self.trigger_emergency_override("NS")
                    else:  # EW direction
                        self.trigger_emergency_override("EW")

        # Handle emergency override timeout
        if self.emergency_override:
            if current_time - self.emergency_override_start > self.emergency_override_duration:
                self.emergency_override = False
                self.emergency_override_direction = None
                self.timer = current_time  # Reset timer for normal operation
            else:
                return  # Don't change lights during emergency override

        # Handle all-red clearance phase (safety interval between phases)
        if self.in_all_red:
            if current_time - self.all_red_start_time > self.all_red_duration:
                # All-red finished, switch to next green phase
                self.in_all_red = False
                if self.current_phase == "NS_GREEN":
                    self.current_phase = "EW_GREEN"
                    self.ns_state = "RED"
                    self.ew_state = "GREEN"
                else:
                    self.current_phase = "NS_GREEN"
                    self.ns_state = "GREEN"
                    self.ew_state = "RED"
                self.timer = current_time
            return

        # Handle yellow transition
        if self.in_yellow_transition:
            if current_time - self.yellow_start_time > self.yellow_duration:
                # Yellow finished, enter all-red clearance
                self.in_yellow_transition = False
                self.in_all_red = True
                self.all_red_start_time = current_time
                # Set both to red during clearance
                self.ns_state = "RED"
                self.ew_state = "RED"
            return

        # Check if current green phase should end
        if self.current_phase == "NS_GREEN":
            green_time = self.get_adaptive_green_time(self.ns_vehicle_count)
            if elapsed > green_time:
                # Start yellow transition for NS direction
                self.in_yellow_transition = True
                self.yellow_start_time = current_time
                self.ns_state = "YELLOW"
                # EW stays red
        else:  # EW_GREEN
            green_time = self.get_adaptive_green_time(self.ew_vehicle_count)
            if elapsed > green_time:
                # Start yellow transition for EW direction
                self.in_yellow_transition = True
                self.yellow_start_time = current_time
                self.ew_state = "YELLOW"
                # NS stays red

    def is_red_for_direction(self, angle):
        """Check if the light is red for a given travel direction"""
        angle_norm = angle % 360
        if angle_norm in [90, 270]:  # North-South
            return self.ns_state == "RED"
        else:  # East-West
            return self.ew_state == "RED"

    def is_yellow_for_direction(self, angle):
        """Check if the light is yellow for a given travel direction"""
        angle_norm = angle % 360
        if angle_norm in [90, 270]:  # North-South
            return self.ns_state == "YELLOW"
        else:  # East-West
            return self.ew_state == "YELLOW"

    def is_at_intersection(self, x, y, threshold=50):
        return abs(x - self.x) < threshold and abs(y - self.y) < threshold

    def draw(self):
        """Draw traffic lights at all four corners of intersection"""
        offset = TILE_SIZE * 0.4  # Position lights at corners

        # Draw 4 traffic lights at intersection corners
        positions = [
            (self.x + offset, self.y + offset, "NS"),  # NE corner - for NS traffic
            (self.x - offset, self.y - offset, "NS"),  # SW corner - for NS traffic
            (self.x + offset, self.y - offset, "EW"),  # SE corner - for EW traffic
            (self.x - offset, self.y + offset, "EW"),  # NW corner - for EW traffic
        ]

        for px, py, direction in positions:
            glPushMatrix()
            glTranslatef(px, py, 0)

            # Pole
            glColor3f(0.25, 0.25, 0.25)
            glPushMatrix()
            glTranslatef(0, 0, 15)
            glScalef(2, 2, 30)
            glutSolidCube(1)
            glPopMatrix()

            # Light housing
            glTranslatef(0, 0, 32)
            glColor3f(0.15, 0.15, 0.15)
            glPushMatrix()
            glScalef(6, 6, 15)
            glutSolidCube(1)
            glPopMatrix()

            # Determine light color based on direction
            if direction == "NS":
                state = self.ns_state
            else:
                state = self.ew_state

            # Draw the light
            if state == "RED":
                glColor3f(1, 0, 0)
            elif state == "YELLOW":
                glColor3f(1, 0.8, 0)
            else:  # GREEN
                glColor3f(0, 1, 0)

            glutSolidSphere(4, 12, 12)

            glPopMatrix()


# Legacy TrafficLight class for compatibility
class TrafficLight:
    """Wrapper for backward compatibility - uses IntersectionController"""

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.pos = [x, y, 20.0]
        self.controller = None  # Will be set by intersection system
        self.state = "RED"
        self.is_red = True
        self.vehicle_count = 0

    def update(self, all_vehicles):
        # Updated by IntersectionController
        pass

    def is_at_intersection(self, x, y, threshold=50):
        return abs(x - self.x) < threshold and abs(y - self.y) < threshold

    def draw(self):
        # Drawing handled by IntersectionController
        pass


# =============================================================================
# VEHICLE CLASS
# =============================================================================


class Vehicle:
    def __init__(self, x, y, is_player=False, color=None, is_emergency=False):
        self.x = x
        self.y = y
        self.angle = 0 if is_player else random.choice([0, 90, 180, 270])
        self.speed = 0
        self.target_speed = 0
        self.is_player = is_player
        self.engine_on = True
        self.crashed = False
        self.crash_time = 0  # Time when crash occurred (for despawn timer)
        self.is_emergency = is_emergency  # Emergency vehicle flag

        # Set color
        if is_emergency:
            self.color = [1.0, 1.0, 1.0]  # White base for emergency vehicles
            self.siren_phase = random.random() * 2 * math.pi  # Random start phase for flashing
        elif color:
            self.color = color
        elif is_player:
            self.color = [1, 0.2, 0.2]
        else:
            self.color = [
                random.random() * 0.5 + 0.3,
                random.random() * 0.5 + 0.3,
                random.random() * 0.5 + 0.3,
            ]

        # Speed settings - increased for larger roads
        if is_emergency:
            self.max_speed = 6.0  # Emergency vehicles are faster
        elif is_player:
            self.max_speed = 8.0  # Faster player car for bigger roads
        else:
            # Some AI vehicles are potential speeders
            if random.random() < 0.15:
                self.max_speed = random.uniform(4.0, 5.5)
            else:
                self.max_speed = random.uniform(2.5, 3.5)

        # Violator flag - 5% of NPCs ignore red/yellow signals (from member3)
        self.is_violator = (random.random() < VIOLATOR_RATE) if (not is_player and not is_emergency) else False

        # AI Speeder flag - 2% of AI cars will overspeed and may cause accidents
        self.is_speeder = (random.random() < AI_OVERSPEEDING_RATE) if (not is_player and not is_emergency) else False

        # State tracking
        self.at_intersection = False
        self.is_overspeeding = False
        self.lane_offset = LANE_OFFSET

        # Apply initial lane offset
        self._apply_lane_offset()

    def _apply_lane_offset(self):
        """Apply lane offset based on direction (right-hand traffic)"""
        if self.angle == 0:  # Moving East
            self.y -= self.lane_offset
        elif self.angle == 180:  # Moving West
            self.y += self.lane_offset
        elif self.angle == 90:  # Moving North
            self.x += self.lane_offset
        elif self.angle == 270:  # Moving South
            self.x -= self.lane_offset

    def _get_lane_offset_for_angle(self, angle):
        """Get lane offset position for a given angle"""
        offset_x, offset_y = 0, 0
        if angle == 0:
            offset_y = -self.lane_offset
        elif angle == 180:
            offset_y = self.lane_offset
        elif angle == 90:
            offset_x = self.lane_offset
        elif angle == 270:
            offset_x = -self.lane_offset
        return offset_x, offset_y

    def update(self, all_vehicles, all_lights):
        """Update vehicle state"""
        global violation_detected, player_lives, has_deducted_life, game_state

        if self.crashed:
            self.speed = 0
            return

        if not self.engine_on:
            self.target_speed = 0

        # Store previous position for road checking
        prev_x, prev_y = self.x, self.y

        # Get current tile position
        row, col = get_tile_coords(self.x, self.y)
        tile_center_x = col * TILE_SIZE + TILE_SIZE / 2
        tile_center_y = row * TILE_SIZE + TILE_SIZE / 2
        dist_to_center = math.sqrt(
            (self.x - tile_center_x) ** 2 + (self.y - tile_center_y) ** 2
        )

        if self.is_player:
            self._update_player(all_lights)
        else:
            self._update_ai(
                all_vehicles,
                all_lights,
                row,
                col,
                tile_center_x,
                tile_center_y,
                dist_to_center,
            )

        # Check overspeeding
        self.is_overspeeding = self.speed > SPEED_LIMIT

        # Collision detection - always check for collisions when moving
        if self.speed > 0.5:
            self._check_collision(all_vehicles)

        # Apply speed changes (smooth acceleration/deceleration)
        if self.is_player:
            if self.speed < self.target_speed:
                self.speed = min(self.target_speed, self.speed + 0.12)
            else:
                self.speed = max(self.target_speed, self.speed - 0.15)

        # Weather effects on speed
        weather_multiplier = 1.0
        if weather_raining:
            weather_multiplier *= 0.8  # 20% slower in rain
        if weather_fog:
            weather_multiplier *= 0.9  # 10% slower in fog

        actual_speed = self.speed * weather_multiplier

        # Movement
        rad = math.radians(self.angle)
        new_x = self.x + math.cos(rad) * actual_speed
        new_y = self.y + math.sin(rad) * actual_speed

        # Apply lane correction to keep vehicles in proper lane (right-hand traffic)
        # Vehicles should stay on the right side of the road based on their direction
        row, col = get_tile_coords(new_x, new_y)
        if is_road(row, col):
            tile_center_x = col * TILE_SIZE + TILE_SIZE / 2
            tile_center_y = row * TILE_SIZE + TILE_SIZE / 2

            # Determine if this is a horizontal or vertical road segment
            h_road = is_road(row, col - 1) or is_road(row, col + 1)
            v_road = is_road(row - 1, col) or is_road(row + 1, col)

            # For horizontal roads (East-West traffic)
            if h_road and not v_road:
                if self.angle == 0:  # Going East - use bottom lane (lower y)
                    target_y = tile_center_y - LANE_OFFSET
                    new_y = new_y * 0.85 + target_y * 0.15  # Smooth correction
                elif self.angle == 180:  # Going West - use top lane (higher y)
                    target_y = tile_center_y + LANE_OFFSET
                    new_y = new_y * 0.85 + target_y * 0.15

            # For vertical roads (North-South traffic)
            if v_road and not h_road:
                if self.angle == 90:  # Going North - use right lane (higher x)
                    target_x = tile_center_x + LANE_OFFSET
                    new_x = new_x * 0.85 + target_x * 0.15
                elif self.angle == 270:  # Going South - use left lane (lower x)
                    target_x = tile_center_x - LANE_OFFSET
                    new_x = new_x * 0.85 + target_x * 0.15

        # Check if new position is on road
        if is_position_on_road(new_x, new_y):
            self.x = new_x
            self.y = new_y
        else:
            # Player tried to go off road - don't allow it
            if self.is_player:
                # Stop the car and keep on road
                self.speed = 0
                self.target_speed = 0
                # Keep previous position (stay on road)
                # Find nearest road position if somehow off road
                if not is_position_on_road(self.x, self.y):
                    self.x, self.y = get_nearest_road_position(self.x, self.y)
            else:
                # AI - try to turn back onto road
                self.x, self.y = get_nearest_road_position(new_x, new_y)
                # Pick a valid direction
                new_row, new_col = get_tile_coords(self.x, self.y)
                available = get_available_directions(new_row, new_col, self.angle)
                if available:
                    self.angle = available[0]

        # Keep vehicles within map bounds - don't wrap, just stop at edges
        limit_x = len(CITY_LAYOUT[0]) * TILE_SIZE
        limit_y = len(CITY_LAYOUT) * TILE_SIZE

        # Boundary checking - keep cars on the map
        # AI turns left or right (not 180) to avoid traffic jams
        if self.x >= limit_x - TILE_SIZE / 2:
            self.x = limit_x - TILE_SIZE / 2
            if not self.is_player:
                # AI turns left or right at map edge (randomly choose)
                self.angle = random.choice([90, 270])  # Turn north or south
            else:
                self.speed = 0
                self.target_speed = 0
        if self.x <= TILE_SIZE / 2:
            self.x = TILE_SIZE / 2
            if not self.is_player:
                # AI turns left or right at map edge
                self.angle = random.choice([90, 270])  # Turn north or south
            else:
                self.speed = 0
                self.target_speed = 0
        if self.y >= limit_y - TILE_SIZE / 2:
            self.y = limit_y - TILE_SIZE / 2
            if not self.is_player:
                # AI turns left or right at map edge
                self.angle = random.choice([0, 180])  # Turn east or west
            else:
                self.speed = 0
                self.target_speed = 0
        if self.y <= TILE_SIZE / 2:
            self.y = TILE_SIZE / 2
            if not self.is_player:
                # AI turns left or right at map edge
                self.angle = random.choice([0, 180])  # Turn east or west
            else:
                self.speed = 0
                self.target_speed = 0

    def _update_player(self, all_lights):
        """Update player-specific logic including violation detection"""
        global violation_detected, player_lives, has_deducted_life, game_state, player_crashed
        global key_accel, key_brake

        # Don't process if crashed
        if player_crashed:
            self.speed = 0
            self.target_speed = 0
            return

        # Handle key-hold acceleration/braking (from member3)
        if key_accel and self.engine_on:
            self.target_speed = min(self.max_speed, self.target_speed + 0.08)
        if key_brake:
            self.target_speed = max(0.0, self.target_speed - 0.12)

        # Check for pothole collision - causes accident
        for pothole in potholes:
            if pothole.contains(self.x, self.y):
                if not player_crashed:
                    self.speed = 0
                    self.crashed = True
                    self.crash_time = time.time()

                    # Create accident at pothole location
                    accidents.append({
                        'x': pothole.x,
                        'y': pothole.y,
                        'time': time.time(),
                        'reason': 'POTHOLE ACCIDENT'
                    })

                    # Create road block
                    road_blocks.append({
                        'x': pothole.x,
                        'y': pothole.y,
                        'time': time.time()
                    })

                    lose_life("Hit pothole - ACCIDENT!")
                break

        # Check for pedestrian collision
        for ped in pedestrians:
            dx = self.x - ped.x
            dy = self.y - ped.y
            if (dx*dx + dy*dy) <= ((20.0 + ped.radius)**2):
                if not player_crashed:
                    accidents.append({
                        'x': ped.x,
                        'y': ped.y,
                        'time': time.time(),
                        'reason': 'PEDESTRIAN HIT'
                    })
                    lose_life("Hit pedestrian")
                break

        # Check for red light violation using intersection controllers
        for controller in intersection_controllers:
            if controller.is_at_intersection(self.x, self.y, threshold=40):
                if controller.is_red_for_direction(self.angle) and self.speed > 0.5:
                    if not violation_detected:
                        violation_detected = True
                        if not has_deducted_life and not player_crashed:
                            lose_life("Red light violation")
                            has_deducted_life = True
                    return

        # Reset violation flags when not in intersection
        violation_detected = False
        has_deducted_life = False

    def _update_ai(
        self,
        all_vehicles,
        all_lights,
        row,
        col,
        tile_center_x,
        tile_center_y,
        dist_to_center,
    ):
        """Update AI vehicle behavior"""
        should_stop = False
        should_slow = False

        # Check for pothole collision - AI vehicles can also crash on potholes
        for pothole in potholes:
            if pothole.contains(self.x, self.y) and not self.crashed:
                self.speed = 0
                self.crashed = True
                self.crash_time = time.time()

                # Create accident at pothole location
                accidents.append({
                    'x': pothole.x,
                    'y': pothole.y,
                    'time': time.time(),
                    'reason': 'AI POTHOLE ACCIDENT'
                })

                # Create road block
                road_blocks.append({
                    'x': pothole.x,
                    'y': pothole.y,
                    'time': time.time()
                })

                add_alert("AI vehicle hit pothole - ACCIDENT!")
                return  # Stop processing this vehicle

        # 1. Check for accidents and road blocks ahead - vehicles must wait
        rad = math.radians(self.angle)
        look_ahead_x = self.x + math.cos(rad) * 80
        look_ahead_y = self.y + math.sin(rad) * 80

        for accident in accidents:
            ax, ay = accident['x'], accident['y']
            # Check if accident is ahead of us
            dx = ax - self.x
            dy = ay - self.y
            distance = math.sqrt(dx * dx + dy * dy)
            if distance < 120 and distance > 0:
                dot = (dx * math.cos(rad) + dy * math.sin(rad)) / distance
                if dot > 0.5:  # Accident is ahead
                    should_stop = True
                    break

        for block in road_blocks:
            bx, by = block['x'], block['y']
            dx = bx - self.x
            dy = by - self.y
            distance = math.sqrt(dx * dx + dy * dy)
            if distance < 100 and distance > 0:
                dot = (dx * math.cos(rad) + dy * math.sin(rad)) / distance
                if dot > 0.5:  # Block is ahead
                    should_stop = True
                    break

        # 2. Check for vehicles ahead (collision avoidance)
        for other in all_vehicles:
            if other is self:
                continue

            dx = other.x - self.x
            dy = other.y - self.y
            distance = math.sqrt(dx * dx + dy * dy)

            # Stop for crashed vehicles - increased distance
            if other.crashed and distance < 60:
                if distance > 0:
                    dot = (dx * math.cos(rad) + dy * math.sin(rad)) / distance
                    if dot > 0.3:  # Crashed car is ahead
                        should_stop = True
                        break

            # Check if vehicle is ahead
            if distance > 0:
                dot = (dx * math.cos(rad) + dy * math.sin(rad)) / distance
                if dot > 0.7:  # Vehicle is ahead
                    if distance < 30:
                        should_stop = True
                        break
                    elif distance < 60:
                        should_slow = True

        # 2. Check traffic lights using intersection controllers
        # Emergency vehicles slow down but don't stop at red lights
        # Violators (5%) ignore red/yellow signals (from member3)
        for controller in intersection_controllers:
            if controller.is_at_intersection(self.x, self.y, threshold=60):
                # Check if light is red or yellow for our direction
                if controller.is_red_for_direction(
                    self.angle
                ) or controller.is_yellow_for_direction(self.angle):
                    rad = math.radians(self.angle)
                    dot = (controller.x - self.x) * math.cos(rad) + (
                        controller.y - self.y
                    ) * math.sin(rad)
                    if dot > 0:  # Intersection is ahead
                        if self.is_emergency:
                            should_slow = True  # Emergency vehicles slow down but don't stop
                        elif self.is_violator:
                            pass  # Violators ignore the signal!
                        else:
                            should_stop = True
                        break

        # 3. Traffic density speed control
        nearby_vehicles = 0
        for other in all_vehicles:
            if other is self:
                continue
            dist = math.sqrt((other.x - self.x) ** 2 + (other.y - self.y) ** 2)
            if dist < 100:
                nearby_vehicles += 1

        # Adjust max speed based on traffic density
        density_factor = max(0.5, 1.0 - nearby_vehicles * 0.1)
        adjusted_max_speed = self.max_speed * density_factor

        # 4. Apply speed changes
        if should_stop:
            self.speed = max(0, self.speed - 0.3)
        elif should_slow:
            target = adjusted_max_speed * 0.5
            if self.speed > target:
                self.speed = max(target, self.speed - 0.15)
            else:
                self.speed = min(target, self.speed + 0.1)
        else:
            # AI speeders will exceed speed limit and cause accidents
            if self.is_speeder:
                # Speeders go faster than normal, exceeding speed limit
                speeder_max = min(self.max_speed * 1.5, SPEED_LIMIT * 1.8)
                self.speed = min(self.speed + 0.2, speeder_max)
            else:
                self.speed = min(self.speed + 0.15, adjusted_max_speed)

        # Check overspeeding for AI
        self.is_overspeeding = self.speed > SPEED_LIMIT

        # AI speeders can also cause collisions
        if self.is_speeder and self.is_overspeeding:
            self._check_collision(all_vehicles)

        # 5. Automatic route selection at intersections
        if dist_to_center < 12 and not self.at_intersection:
            self.at_intersection = True
            # Snap to center
            self.x, self.y = tile_center_x, tile_center_y

            # Choose new direction
            available_dirs = get_available_directions(row, col, self.angle)
            if available_dirs:
                new_angle = random.choice(available_dirs)
                self.angle = new_angle

                # Apply lane offset for new direction
                offset_x, offset_y = self._get_lane_offset_for_angle(new_angle)
                self.x += offset_x
                self.y += offset_y
        elif dist_to_center > 20:
            self.at_intersection = False

    def _check_collision(self, all_vehicles):
        """Check for collision with other vehicles"""
        global player_crashed

        for other in all_vehicles:
            if other is self or other.crashed:
                continue

            dx = other.x - self.x
            dy = other.y - self.y
            distance = math.sqrt(dx * dx + dy * dy)

            # Check if vehicles are close enough to collide
            if distance < VEHICLE_COLLISION_RADIUS:
                # Collision detected!
                # Higher chance if overspeeding, but always possible
                crash_chance = OVERSPEEDING_CRASH_CHANCE if not self.is_overspeeding else 0.5

                # For player, always crash on collision
                if self.is_player or other.is_player or random.random() < crash_chance:
                    # Crash!
                    self.crashed = True
                    self.crash_time = time.time()  # Record crash time
                    self.speed = 0
                    other.crashed = True
                    other.crash_time = time.time()  # Record crash time
                    other.speed = 0

                    accident_x = (self.x + other.x) / 2
                    accident_y = (self.y + other.y) / 2

                    if self.is_player:
                        player_crashed = True
                        lose_life("Car collision")

                    accidents.append(
                        {
                            "x": accident_x,
                            "y": accident_y,
                            "time": time.time(),
                            "reason": "COLLISION",
                        }
                    )

                    # Create road block at accident location to block traffic
                    road_blocks.append({
                        'x': accident_x,
                        'y': accident_y,
                        'time': time.time()
                    })

                    add_alert(f"CRASH! Road blocked - vehicles waiting!")
                    return

    def draw(self, highlight_player=False, aerial_view=False):
        """Draw the vehicle"""
        glPushMatrix()
        glTranslatef(self.x, self.y, 5)
        glRotatef(self.angle, 0, 0, 1)

        # Scale up cars in aerial view for better visibility
        if aerial_view:
            glScalef(1.8, 1.8, 1.8)

        draw_color = self.color.copy()

        if self.crashed:
            draw_color = [0.15, 0.15, 0.15]
        elif self.is_emergency:
            # Emergency vehicle - white body
            draw_color = [1.0, 1.0, 1.0]
        elif self.is_overspeeding:
            # Red tint for overspeeding
            draw_color = [
                min(1, draw_color[0] + 0.4),
                draw_color[1] * 0.6,
                draw_color[2] * 0.6,
            ]

        glColor3fv(draw_color)

        # Car body
        glPushMatrix()
        glScalef(22, 11, 8)
        glutSolidCube(1)
        glPopMatrix()

        # Roof
        if not self.crashed:
            glPushMatrix()
            glTranslatef(-2, 0, 6)
            if self.is_emergency:
                glColor3f(0.9, 0.9, 0.9)  # Light gray roof for emergency
            else:
                glColor3f(draw_color[0] * 0.7, draw_color[1] * 0.7, draw_color[2] * 0.7)
            glScalef(12, 9, 5)
            glutSolidCube(1)
            glPopMatrix()

        # Emergency vehicle flashing lights (red and blue) - highly visible
        if self.is_emergency and not self.crashed:
            glDisable(GL_LIGHTING)  # Disable lighting for bright colors

            # Faster flashing effect
            flash_phase = (time.time() * 6 + self.siren_phase) % 1.0

            # Light bar on top of vehicle
            glPushMatrix()
            glTranslatef(0, 0, 10)

            # Left side - Red light
            glPushMatrix()
            glTranslatef(-4, 3, 0)
            if flash_phase < 0.5:
                glColor3f(1.0, 0.0, 0.0)  # Bright Red
            else:
                glColor3f(0.3, 0.0, 0.0)  # Dim red
            glutSolidSphere(2.5, 10, 10)
            glPopMatrix()

            # Right side - Blue light
            glPushMatrix()
            glTranslatef(-4, -3, 0)
            if flash_phase >= 0.5:
                glColor3f(0.0, 0.0, 1.0)  # Bright Blue
            else:
                glColor3f(0.0, 0.0, 0.3)  # Dim blue
            glutSolidSphere(2.5, 10, 10)
            glPopMatrix()

            # Front left - Red
            glPushMatrix()
            glTranslatef(2, 3, 0)
            if flash_phase < 0.5:
                glColor3f(1.0, 0.0, 0.0)  # Bright Red
            else:
                glColor3f(0.3, 0.0, 0.0)  # Dim red
            glutSolidSphere(2.5, 10, 10)
            glPopMatrix()

            # Front right - Blue
            glPushMatrix()
            glTranslatef(2, -3, 0)
            if flash_phase >= 0.5:
                glColor3f(0.0, 0.0, 1.0)  # Bright Blue
            else:
                glColor3f(0.0, 0.0, 0.3)  # Dim blue
            glutSolidSphere(2.5, 10, 10)
            glPopMatrix()

            glPopMatrix()
            glEnable(GL_LIGHTING)

        # Violator mark (red dot on top) - from member3
        if hasattr(self, 'is_violator') and self.is_violator and not self.crashed:
            glDisable(GL_LIGHTING)
            glColor3f(1, 0, 0)
            glPushMatrix()
            glTranslatef(0, 0, 12)
            glutSolidSphere(2.5, 10, 10)
            glPopMatrix()
            glEnable(GL_LIGHTING)

        # Speeder mark (orange dot on top) - for AI cars that overspeed
        if hasattr(self, 'is_speeder') and self.is_speeder and not self.crashed and not self.is_violator:
            glDisable(GL_LIGHTING)
            glColor3f(1, 0.5, 0)  # Orange
            glPushMatrix()
            glTranslatef(0, 0, 12)
            glutSolidSphere(2.5, 10, 10)
            glPopMatrix()
            glEnable(GL_LIGHTING)

        # Headlights
        if not self.crashed and self.engine_on:
            glColor3f(1, 1, 0.8)
            glPushMatrix()
            glTranslatef(11, 4, 0)
            glutSolidSphere(1.5, 6, 6)
            glPopMatrix()
            glPushMatrix()
            glTranslatef(11, -4, 0)
            glutSolidSphere(1.5, 6, 6)
            glPopMatrix()

        glPopMatrix()

        # Draw player highlight (pulsing ring around car) - only in TOP view
        if self.is_player and highlight_player and not self.crashed:
            glPushMatrix()
            glTranslatef(self.x, self.y, 1)
            glDisable(GL_LIGHTING)

            # Pulsing effect
            pulse = (math.sin(time.time() * PLAYER_HIGHLIGHT_PULSE_SPEED) + 1) / 2
            ring_size = 25 + pulse * 8

            # Draw highlight ring
            glColor3f(0, 1, 0.5)  # Bright green
            glLineWidth(3)
            glBegin(GL_LINE_LOOP)
            for i in range(36):
                angle = 2 * math.pi * i / 36
                glVertex3f(math.cos(angle) * ring_size, math.sin(angle) * ring_size, 0)
            glEnd()

            # Draw arrow pointing in direction of travel
            glColor3f(1, 1, 0)  # Yellow arrow
            rad = math.radians(self.angle)
            arrow_len = 35
            glLineWidth(2)
            glBegin(GL_LINES)
            # Arrow shaft
            glVertex3f(0, 0, 2)
            glVertex3f(math.cos(rad) * arrow_len, math.sin(rad) * arrow_len, 2)
            # Arrow head
            head_angle1 = rad + math.pi * 0.8
            head_angle2 = rad - math.pi * 0.8
            glVertex3f(math.cos(rad) * arrow_len, math.sin(rad) * arrow_len, 2)
            glVertex3f(
                math.cos(rad) * arrow_len + math.cos(head_angle1) * 10,
                math.sin(rad) * arrow_len + math.sin(head_angle1) * 10,
                2,
            )
            glVertex3f(math.cos(rad) * arrow_len, math.sin(rad) * arrow_len, 2)
            glVertex3f(
                math.cos(rad) * arrow_len + math.cos(head_angle2) * 10,
                math.sin(rad) * arrow_len + math.sin(head_angle2) * 10,
                2,
            )
            glEnd()
            glLineWidth(1)

            glEnable(GL_LIGHTING)
            glPopMatrix()


# =============================================================================
# ENVIRONMENT DRAWING
# =============================================================================


def draw_city():
    """Draw the city environment"""
    # Draw roads - dark asphalt
    glColor3f(0.2, 0.2, 0.22)
    glBegin(GL_QUADS)
    for row in range(len(CITY_LAYOUT)):
        for col in range(len(CITY_LAYOUT[0])):
            if CITY_LAYOUT[row][col] == 1:
                x = col * TILE_SIZE
                y = row * TILE_SIZE
                glVertex3f(x, y, 0)
                glVertex3f(x + TILE_SIZE, y, 0)
                glVertex3f(x + TILE_SIZE, y + TILE_SIZE, 0)
                glVertex3f(x, y + TILE_SIZE, 0)
    glEnd()

    # Draw road edges (white lines on sides)
    glColor3f(0.9, 0.9, 0.9)
    glLineWidth(3)
    glBegin(GL_LINES)
    for row in range(len(CITY_LAYOUT)):
        for col in range(len(CITY_LAYOUT[0])):
            if CITY_LAYOUT[row][col] == 1:
                x = col * TILE_SIZE
                y = row * TILE_SIZE

                h_road = is_road(row, col - 1) and is_road(row, col + 1)
                v_road = is_road(row - 1, col) and is_road(row + 1, col)

                edge_inset = 5

                if h_road and not v_road:
                    # Horizontal road - draw top and bottom edge lines
                    glVertex3f(x, y + edge_inset, 0.2)
                    glVertex3f(x + TILE_SIZE, y + edge_inset, 0.2)
                    glVertex3f(x, y + TILE_SIZE - edge_inset, 0.2)
                    glVertex3f(x + TILE_SIZE, y + TILE_SIZE - edge_inset, 0.2)
                elif v_road and not h_road:
                    # Vertical road - draw left and right edge lines
                    glVertex3f(x + edge_inset, y, 0.2)
                    glVertex3f(x + edge_inset, y + TILE_SIZE, 0.2)
                    glVertex3f(x + TILE_SIZE - edge_inset, y, 0.2)
                    glVertex3f(x + TILE_SIZE - edge_inset, y + TILE_SIZE, 0.2)
    glEnd()

    # Draw lane dividers (yellow dashed center line)
    glColor3f(1, 0.9, 0.2)
    glLineWidth(2)
    glBegin(GL_LINES)
    for row in range(len(CITY_LAYOUT)):
        for col in range(len(CITY_LAYOUT[0])):
            if CITY_LAYOUT[row][col] == 1:
                x = col * TILE_SIZE + TILE_SIZE / 2
                y = row * TILE_SIZE + TILE_SIZE / 2

                h_road = is_road(row, col - 1) and is_road(row, col + 1)
                v_road = is_road(row - 1, col) and is_road(row + 1, col)

                if h_road and not v_road:
                    # More dashes for longer tiles
                    num_dashes = 4
                    dash_len = TILE_SIZE / (num_dashes * 2)
                    for i in range(num_dashes):
                        start_x = x - TILE_SIZE / 2 + i * (TILE_SIZE / num_dashes)
                        end_x = start_x + dash_len
                        glVertex3f(start_x, y, 0.15)
                        glVertex3f(end_x, y, 0.15)
                elif v_road and not h_road:
                    num_dashes = 4
                    dash_len = TILE_SIZE / (num_dashes * 2)
                    for i in range(num_dashes):
                        start_y = y - TILE_SIZE / 2 + i * (TILE_SIZE / num_dashes)
                        end_y = start_y + dash_len
                        glVertex3f(x, start_y, 0.15)
                        glVertex3f(x, end_y, 0.15)
    glEnd()
    glLineWidth(1)

    # Draw footpaths (sidewalks) adjacent to roads
    glColor3f(0.55, 0.55, 0.52)  # Gray sidewalk color
    glBegin(GL_QUADS)
    for row in range(len(CITY_LAYOUT)):
        for col in range(len(CITY_LAYOUT[0])):
            if CITY_LAYOUT[row][col] == 0:  # Not a road (building area)
                # Check if adjacent to road
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    if is_road(row + dr, col + dc):
                        # Draw footpath on this edge
                        x = col * TILE_SIZE
                        y = row * TILE_SIZE

                        if dr == -1:  # Road is above, footpath on top edge
                            glVertex3f(x, y + TILE_SIZE - FOOTPATH_WIDTH * 1.5, 0.1)
                            glVertex3f(x + TILE_SIZE, y + TILE_SIZE - FOOTPATH_WIDTH * 1.5, 0.1)
                            glVertex3f(x + TILE_SIZE, y + TILE_SIZE, 0.1)
                            glVertex3f(x, y + TILE_SIZE, 0.1)
                        elif dr == 1:  # Road is below, footpath on bottom edge
                            glVertex3f(x, y, 0.1)
                            glVertex3f(x + TILE_SIZE, y, 0.1)
                            glVertex3f(x + TILE_SIZE, y + FOOTPATH_WIDTH * 1.5, 0.1)
                            glVertex3f(x, y + FOOTPATH_WIDTH * 1.5, 0.1)
                        elif dc == -1:  # Road is left, footpath on left edge
                            glVertex3f(x + TILE_SIZE - FOOTPATH_WIDTH * 1.5, y, 0.1)
                            glVertex3f(x + TILE_SIZE, y, 0.1)
                            glVertex3f(x + TILE_SIZE, y + TILE_SIZE, 0.1)
                            glVertex3f(x + TILE_SIZE - FOOTPATH_WIDTH * 1.5, y + TILE_SIZE, 0.1)
                        elif dc == 1:  # Road is right, footpath on right edge
                            glVertex3f(x, y, 0.1)
                            glVertex3f(x + FOOTPATH_WIDTH * 1.5, y, 0.1)
                            glVertex3f(x + FOOTPATH_WIDTH * 1.5, y + TILE_SIZE, 0.1)
                            glVertex3f(x, y + TILE_SIZE, 0.1)
    glEnd()

    # Draw buildings - larger and taller for bigger tiles (with smaller footprint to show footpath)
    for row in range(len(CITY_LAYOUT)):
        for col in range(len(CITY_LAYOUT[0])):
            if CITY_LAYOUT[row][col] == 0:
                x = col * TILE_SIZE + TILE_SIZE / 2
                y = row * TILE_SIZE + TILE_SIZE / 2
                height = 50 + ((row * 7 + col * 13) % 80)  # Taller buildings

                # Calculate building inset based on adjacent roads (leave room for footpath)
                inset = FOOTPATH_WIDTH * 2.0
                building_size = TILE_SIZE - inset * 2

                # Vary building colors
                color_seed = (row * 3 + col * 7) % 5
                colors = [
                    (0.75, 0.75, 0.78),
                    (0.82, 0.80, 0.75),
                    (0.70, 0.75, 0.80),
                    (0.78, 0.78, 0.72),
                    (0.72, 0.72, 0.76),
                ]
                glColor3fv(colors[color_seed])

                glPushMatrix()
                glTranslatef(x, y, height / 2)
                glScalef(
                    building_size, building_size, height
                )  # Smaller to leave room for footpath
                glutSolidCube(1)
                glPopMatrix()

    # Draw rain
    if weather_raining and rain_particles:
        glDisable(GL_LIGHTING)
        glColor3f(0.6, 0.6, 0.9)
        glLineWidth(1)
        glBegin(GL_LINES)
        for rx, ry, rz in rain_particles:
            glVertex3f(rx, ry, rz)
            glVertex3f(rx, ry, rz - 15)
        glEnd()
        glEnable(GL_LIGHTING)

    # Draw pedestrians (from member3)
    for ped in pedestrians:
        ped.draw()

    # Draw potholes (from member3)
    for pothole in potholes:
        pothole.draw()

    # Draw traffic lights
    for light in traffic_lights:
        light.draw()

    # Draw accident markers
    for accident in accidents:
        if time.time() - accident["time"] < 30:
            glPushMatrix()
            glTranslatef(accident["x"], accident["y"], 25)
            glDisable(GL_LIGHTING)
            pulse = (math.sin(time.time() * 5) + 1) / 2
            glColor3f(1, pulse * 0.5, 0)
            glutSolidSphere(8, 8, 8)
            glEnable(GL_LIGHTING)
            glPopMatrix()


def draw_minimap():
    """Draw Google Maps style minimap with traffic heatmap and legend"""
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, WINDOW_W, 0, WINDOW_H)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()
    glDisable(GL_LIGHTING)
    glDisable(GL_DEPTH_TEST)

    map_size = 180  # Slightly larger minimap
    padding = 10
    legend_width = 80  # Width for legend

    # Border with Google Maps style
    glColor3f(0.3, 0.3, 0.3)
    glLineWidth(3)
    glBegin(GL_LINE_LOOP)
    glVertex2f(padding - 3, padding - 3)
    glVertex2f(padding + map_size + 3, padding - 3)
    glVertex2f(padding + map_size + 3, padding + map_size + 3)
    glVertex2f(padding - 3, padding + map_size + 3)
    glEnd()
    glLineWidth(1)

    # Background - dark like Google Maps dark mode
    glColor3f(0.12, 0.12, 0.15)
    glBegin(GL_QUADS)
    glVertex2f(padding, padding)
    glVertex2f(padding + map_size, padding)
    glVertex2f(padding + map_size, padding + map_size)
    glVertex2f(padding, padding + map_size)
    glEnd()

    scale_x = map_size / (len(CITY_LAYOUT[0]) * TILE_SIZE)
    scale_y = map_size / (len(CITY_LAYOUT) * TILE_SIZE)

    # Build density grid for heatmap
    density_grid = {}
    for v in vehicles:
        if not v.crashed:
            r, c = get_tile_coords(v.x, v.y)
            density_grid[(r, c)] = density_grid.get((r, c), 0) + 1

    # Draw roads with heatmap coloring (Google Maps traffic style)
    glBegin(GL_QUADS)
    for row in range(len(CITY_LAYOUT)):
        for col in range(len(CITY_LAYOUT[0])):
            if CITY_LAYOUT[row][col] == 1:
                count = density_grid.get((row, col), 0)
                if count == 0:
                    glColor3f(0.25, 0.25, 0.28)  # Dark gray - empty roads
                elif count == 1:
                    glColor3f(0.2, 0.7, 0.3)  # Green - clear
                elif count == 2:
                    glColor3f(0.9, 0.85, 0.2)  # Yellow - moderate
                elif count == 3:
                    glColor3f(1.0, 0.5, 0.0)  # Orange - heavy
                else:
                    glColor3f(0.85, 0.15, 0.15)  # Red - congested

                x = padding + col * TILE_SIZE * scale_x
                y = padding + row * TILE_SIZE * scale_y
                w = TILE_SIZE * scale_x
                h = TILE_SIZE * scale_y

                glVertex2f(x, y)
                glVertex2f(x + w, y)
                glVertex2f(x + w, y + h)
                glVertex2f(x, y + h)
    glEnd()

    # Draw vehicles with different colors based on type
    for i, v in enumerate(vehicles):
        mx = padding + v.x * scale_x
        my = padding + v.y * scale_y

        if v.crashed:
            # Crashed - gray dot
            glColor3f(0.4, 0.4, 0.4)
            glPointSize(4)
            glBegin(GL_POINTS)
            glVertex2f(mx, my)
            glEnd()
        elif v.is_player:
            # Player - cyan with larger marker
            glColor3f(0, 1, 1)
            glPointSize(6)
            glBegin(GL_POINTS)
            glVertex2f(mx, my)
            glEnd()
            # Direction indicator
            rad = math.radians(v.angle)
            glLineWidth(2)
            glBegin(GL_LINES)
            glVertex2f(mx, my)
            glVertex2f(mx + math.cos(rad) * 8, my + math.sin(rad) * 8)
            glEnd()
        elif hasattr(v, 'is_emergency') and v.is_emergency:
            # Emergency vehicle - flashing red/blue, BIGGER marker
            flash = (time.time() * 6) % 2

            # Draw larger outer ring for visibility
            glColor3f(1, 1, 1)  # White outline
            glPointSize(10)
            glBegin(GL_POINTS)
            glVertex2f(mx, my)
            glEnd()

            # Flashing inner dot
            if flash < 1:
                glColor3f(1, 0, 0)  # Red
            else:
                glColor3f(0, 0, 1)  # Blue
            glPointSize(7)
            glBegin(GL_POINTS)
            glVertex2f(mx, my)
            glEnd()

            # Direction indicator for emergency vehicles
            rad = math.radians(v.angle)
            glColor3f(1, 1, 0)  # Yellow direction line
            glLineWidth(2)
            glBegin(GL_LINES)
            glVertex2f(mx, my)
            glVertex2f(mx + math.cos(rad) * 10, my + math.sin(rad) * 10)
            glEnd()
            glLineWidth(1)
        elif v.is_overspeeding:
            # Overspeeding - orange
            glColor3f(1, 0.6, 0)
            glPointSize(4)
            glBegin(GL_POINTS)
            glVertex2f(mx, my)
            glEnd()
        else:
            # Normal vehicle - light green
            glColor3f(0.5, 0.9, 0.5)
            glPointSize(3)
            glBegin(GL_POINTS)
            glVertex2f(mx, my)
            glEnd()
    glPointSize(1)

    # Draw accidents as pulsing red X markers
    glLineWidth(2)
    for accident in accidents:
        if time.time() - accident["time"] < 30:
            mx = padding + accident["x"] * scale_x
            my = padding + accident["y"] * scale_y
            pulse = (math.sin(time.time() * 5) + 1) / 2
            glColor3f(1, pulse * 0.3, pulse * 0.3)
            size = 4 + pulse * 2
            glBegin(GL_LINES)
            glVertex2f(mx - size, my - size)
            glVertex2f(mx + size, my + size)
            glVertex2f(mx - size, my + size)
            glVertex2f(mx + size, my - size)
            glEnd()
    glLineWidth(1)

    # Draw road blocks as orange triangles
    for block in road_blocks:
        bx = padding + block['x'] * scale_x
        by = padding + block['y'] * scale_y
        glColor3f(1, 0.6, 0)
        glBegin(GL_TRIANGLES)
        glVertex2f(bx, by + 5)
        glVertex2f(bx - 4, by - 3)
        glVertex2f(bx + 4, by - 3)
        glEnd()

    # Draw potholes as yellow/brown circles with alert
    for pothole in potholes:
        px = padding + pothole.x * scale_x
        py = padding + pothole.y * scale_y

        # Pulsing alert effect
        pulse = (math.sin(time.time() * 3 + pothole.x) + 1) / 2

        # Draw pothole marker (dark with yellow warning border)
        glColor3f(0.8, 0.6, 0.0)  # Yellow/brown warning color
        radius = 3 + pulse
        glBegin(GL_TRIANGLE_FAN)
        glVertex2f(px, py)
        for i in range(9):
            angle = 2 * math.pi * i / 8
            glVertex2f(px + math.cos(angle) * radius, py + math.sin(angle) * radius)
        glEnd()

        # Inner dark circle
        glColor3f(0.1, 0.1, 0.1)
        inner_radius = 2
        glBegin(GL_TRIANGLE_FAN)
        glVertex2f(px, py)
        for i in range(9):
            angle = 2 * math.pi * i / 8
            glVertex2f(px + math.cos(angle) * inner_radius, py + math.sin(angle) * inner_radius)
        glEnd()

    # Draw congestion alert zones (areas with 3+ vehicles waiting)
    congestion_zones = {}
    for v in vehicles:
        if v.speed < 0.5:  # Vehicle is stopped or very slow
            r, c = get_tile_coords(v.x, v.y)
            key = (r // 3, c // 3)  # Group into larger zones
            congestion_zones[key] = congestion_zones.get(key, 0) + 1

    # Draw congestion alert circles
    for (zone_r, zone_c), count in congestion_zones.items():
        if count >= 3:  # Congestion alert threshold
            zone_x = padding + (zone_c * 3 + 1.5) * TILE_SIZE * scale_x
            zone_y = padding + (zone_r * 3 + 1.5) * TILE_SIZE * scale_y

            # Pulsing congestion alert
            pulse = (math.sin(time.time() * 4) + 1) / 2
            if count >= 5:
                glColor4f(1, 0, 0, 0.5 + pulse * 0.3)  # Red for severe
            else:
                glColor4f(1, 0.6, 0, 0.4 + pulse * 0.3)  # Orange for moderate

            # Draw alert circle
            radius = 8 + count * 1.5
            glBegin(GL_TRIANGLE_FAN)
            glVertex2f(zone_x, zone_y)
            for i in range(17):
                angle = 2 * math.pi * i / 16
                glVertex2f(zone_x + math.cos(angle) * radius, zone_y + math.sin(angle) * radius)
            glEnd()

            # Draw exclamation mark for severe congestion
            if count >= 5:
                glColor3f(1, 1, 1)
                glLineWidth(2)
                glBegin(GL_LINES)
                glVertex2f(zone_x, zone_y + 4)
                glVertex2f(zone_x, zone_y - 1)
                glEnd()
                glPointSize(3)
                glBegin(GL_POINTS)
                glVertex2f(zone_x, zone_y - 4)
                glEnd()
                glLineWidth(1)
    glPointSize(1)

    # Draw traffic heatmap legend
    legend_x = padding + map_size + 10
    legend_y = padding

    # Legend background
    glColor3f(0.15, 0.15, 0.18)
    glBegin(GL_QUADS)
    glVertex2f(legend_x - 5, legend_y - 5)
    glVertex2f(legend_x + legend_width, legend_y - 5)
    glVertex2f(legend_x + legend_width, legend_y + 120)
    glVertex2f(legend_x - 5, legend_y + 120)
    glEnd()

    # Legend title
    glColor3f(1, 1, 1)
    draw_text(legend_x, legend_y + 105, "TRAFFIC", GLUT_BITMAP_HELVETICA_10)

    # Legend items
    legend_items = [
        ([0.2, 0.7, 0.3], "Clear"),
        ([0.9, 0.85, 0.2], "Moderate"),
        ([1.0, 0.5, 0.0], "Heavy"),
        ([0.85, 0.15, 0.15], "Congested"),
        ([1.0, 0.3, 0.0], "! Alert"),
    ]

    for idx, (color, label) in enumerate(legend_items):
        ly = legend_y + 85 - idx * 18
        # Color box
        glColor3fv(color)
        glBegin(GL_QUADS)
        glVertex2f(legend_x, ly)
        glVertex2f(legend_x + 12, ly)
        glVertex2f(legend_x + 12, ly + 10)
        glVertex2f(legend_x, ly + 10)
        glEnd()
        # Label
        glColor3f(0.8, 0.8, 0.8)
        draw_text(legend_x + 16, ly + 2, label, GLUT_BITMAP_HELVETICA_10)

    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)


def draw_hud():
    """Draw heads-up display"""
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, WINDOW_W, 0, WINDOW_H)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()
    glDisable(GL_LIGHTING)
    glDisable(GL_DEPTH_TEST)

    if game_state == "START_SCREEN":
        # Start screen HUD
        glColor3f(1, 1, 1)
        draw_text(
            WINDOW_W // 2 - 180,
            WINDOW_H // 2 + 150,
            "AUTONOMOUS CITY TRAFFIC SIMULATOR",
        )
        glColor3f(1, 1, 0)
        draw_text(
            WINDOW_W // 2 - 120,
            WINDOW_H // 2 + 100,
            "PRESS 1, 2, 3, or 4 TO SELECT CAR",
        )

        # Show car color labels
        glColor3f(1, 0.2, 0.2)
        draw_text(
            WINDOW_W // 2 - 170, WINDOW_H // 2 + 70, "1:Red", GLUT_BITMAP_HELVETICA_12
        )
        glColor3f(0.2, 0.3, 1)
        draw_text(
            WINDOW_W // 2 - 90, WINDOW_H // 2 + 70, "2:Blue", GLUT_BITMAP_HELVETICA_12
        )
        glColor3f(1, 1, 0.2)
        draw_text(
            WINDOW_W // 2 - 10, WINDOW_H // 2 + 70, "3:Yellow", GLUT_BITMAP_HELVETICA_12
        )
        glColor3f(0.9, 0.9, 0.9)
        draw_text(
            WINDOW_W // 2 + 70, WINDOW_H // 2 + 70, "4:White", GLUT_BITMAP_HELVETICA_12
        )

        glColor3f(0.8, 0.8, 0.8)
        draw_text(WINDOW_W // 2 - 180, WINDOW_H // 2 + 40, "DRIVING CONTROLS:")
        glColor3f(0.7, 0.7, 0.7)
        draw_text(
            WINDOW_W // 2 - 180,
            WINDOW_H // 2 + 20,
            "  LEFT/RIGHT Arrows = Steer",
        )
        draw_text(
            WINDOW_W // 2 - 180,
            WINDOW_H // 2 + 0,
            "  UP/DOWN or PgUp/PgDn = Accelerate/Brake",
        )
        draw_text(
            WINDOW_W // 2 - 180,
            WINDOW_H // 2 - 20,
            "  Enter = Engine On/Off | Space = Pause",
        )

        glColor3f(0.8, 0.8, 0.8)
        draw_text(WINDOW_W // 2 - 180, WINDOW_H // 2 - 50, "VIEW CONTROLS:")
        glColor3f(0.5, 1.0, 0.5)
        draw_text(
            WINDOW_W // 2 - 180,
            WINDOW_H // 2 - 70,
            "  V = Cycle Views (Aerial -> 3rd Person -> Racing 1st Person)",
        )
        draw_text(
            WINDOW_W // 2 - 180,
            WINDOW_H // 2 - 90,
            "  E = Cycle Vehicles (in 3rd/1st Person view)",
        )

        glColor3f(0.7, 0.7, 0.7)
        draw_text(
            WINDOW_W // 2 - 180, WINDOW_H // 2 - 120, "OTHER: R=Rain, F=Fog, X=Reset"
        )
    else:
        # Game HUD
        glColor3f(1, 1, 1)
        draw_text(20, WINDOW_H - 30, f"LIVES: {player_lives}")

        # Speed and status
        if vehicles:
            player = vehicles[0]
            speed_text = f"Speed: {player.speed:.1f} / {SPEED_LIMIT}"
            if player.is_overspeeding:
                glColor3f(1, 0.5, 0)
                speed_text += " [OVERSPEEDING!]"
            else:
                glColor3f(0.5, 1, 0.5)
            draw_text(20, WINDOW_H - 55, speed_text)

        # Weather status
        glColor3f(0.7, 0.7, 0.7)
        weather_text = f"Weather: {'Rain ' if weather_raining else ''}{'Fog ' if weather_fog else ''}{'Clear' if not weather_raining and not weather_fog else ''}"
        draw_text(20, WINDOW_H - 80, weather_text)

        # Day/Night and additional info (from member3)
        time_of_day = "Night" if is_night else "Day"
        draw_text(20, WINDOW_H - 130, f"Time: {time_of_day} | Peds: {len(pedestrians)} | Potholes: {len(potholes)}")

        # Crash status
        if player_crashed:
            glColor3f(1, 0.4, 0.4)
            draw_text(20, WINDOW_H - 155, "STATUS: CRASHED (Press T to respawn)")

        # View mode with better labels
        view_labels = {
            "TOP": "AERIAL (Top Down)",
            "THIRD_PERSON": "THIRD PERSON (Behind)",
            "FIRST_PERSON": "FIRST PERSON (Driver)",
        }
        view_label = view_labels.get(view_mode, view_mode)
        draw_text(
            20,
            WINDOW_H - 105,
            f"View: {view_label}",
        )
        if view_mode in ["THIRD_PERSON", "FIRST_PERSON"]:
            v_type = "Player" if vehicles[selected_vehicle_index].is_player else "AI"
            draw_text(
                20,
                WINDOW_H - 125,
                f"Following: {v_type} #{selected_vehicle_index} (Press E to cycle)",
            )

        # Paused indicator
        if not sim_running:
            glColor3f(1, 1, 0)
            draw_text(WINDOW_W // 2 - 50, WINDOW_H // 2, "PAUSED")

        # Violation warning
        if violation_detected:
            glColor3f(1, 0, 0)
            draw_text(WINDOW_W // 2 - 100, WINDOW_H // 2 + 50, "RED LIGHT VIOLATION!")

        # Stats panel (top right) - Enhanced Performance Statistics
        stats_x = WINDOW_W - 220
        stats_y = WINDOW_H - 25

        # Panel background
        glColor4f(0.1, 0.1, 0.15, 0.8)
        glBegin(GL_QUADS)
        glVertex2f(stats_x - 10, WINDOW_H - 185)
        glVertex2f(WINDOW_W - 5, WINDOW_H - 185)
        glVertex2f(WINDOW_W - 5, WINDOW_H - 5)
        glVertex2f(stats_x - 10, WINDOW_H - 5)
        glEnd()

        # Panel title
        glColor3f(1, 1, 0.8)
        draw_text(stats_x, stats_y, "PERFORMANCE STATS", GLUT_BITMAP_HELVETICA_12)

        # Calculate statistics
        total_vehicles = len(vehicles)
        crashed_count = len([v for v in vehicles if v.crashed])
        active_count = total_vehicles - crashed_count
        overspeeding_count = len([v for v in vehicles if v.is_overspeeding and not v.crashed])
        emergency_count = len([v for v in vehicles if hasattr(v, 'is_emergency') and v.is_emergency and not v.crashed])

        # Calculate average speed
        moving_vehicles = [v for v in vehicles if not v.crashed and v.speed > 0]
        if moving_vehicles:
            avg_speed = sum(v.speed for v in moving_vehicles) / len(moving_vehicles)
        else:
            avg_speed = 0

        # Calculate traffic flow efficiency (% of vehicles moving at good speed)
        if active_count > 0:
            efficient_vehicles = len([v for v in vehicles if not v.crashed and v.speed > 1.5 and not v.is_overspeeding])
            flow_efficiency = (efficient_vehicles / active_count) * 100
        else:
            flow_efficiency = 0

        # Display stats with color coding
        line_height = 16
        y_offset = stats_y - 20

        # Total Vehicles
        glColor3f(0.8, 0.8, 0.8)
        draw_text(stats_x, y_offset, f"Total Vehicles: {total_vehicles}", GLUT_BITMAP_HELVETICA_12)
        y_offset -= line_height

        # Active Vehicles
        glColor3f(0.5, 1, 0.5)
        draw_text(stats_x, y_offset, f"Active: {active_count}", GLUT_BITMAP_HELVETICA_12)
        y_offset -= line_height

        # Crashed Vehicles
        glColor3f(0.6, 0.6, 0.6)
        draw_text(stats_x, y_offset, f"Crashed: {crashed_count}", GLUT_BITMAP_HELVETICA_12)
        y_offset -= line_height

        # Overspeeding (orange if any)
        if overspeeding_count > 0:
            glColor3f(1, 0.6, 0)
        else:
            glColor3f(0.5, 0.8, 0.5)
        draw_text(stats_x, y_offset, f"Overspeeding: {overspeeding_count}", GLUT_BITMAP_HELVETICA_12)
        y_offset -= line_height

        # Emergency Vehicles (red/blue if any)
        if emergency_count > 0:
            flash = (time.time() * 4) % 2
            if flash < 1:
                glColor3f(1, 0.3, 0.3)
            else:
                glColor3f(0.3, 0.3, 1)
        else:
            glColor3f(0.7, 0.7, 0.7)
        draw_text(stats_x, y_offset, f"Emergency: {emergency_count}", GLUT_BITMAP_HELVETICA_12)
        y_offset -= line_height

        # Total Accidents (red if any)
        if len(accidents) > 0:
            glColor3f(1, 0.3, 0.3)
        else:
            glColor3f(0.5, 0.8, 0.5)
        draw_text(stats_x, y_offset, f"Accidents: {len(accidents)}", GLUT_BITMAP_HELVETICA_12)
        y_offset -= line_height

        # Average Speed
        glColor3f(0.7, 0.9, 1)
        draw_text(stats_x, y_offset, f"Avg Speed: {avg_speed:.1f}", GLUT_BITMAP_HELVETICA_12)
        y_offset -= line_height

        # Traffic Flow Efficiency with color gradient
        if flow_efficiency >= 70:
            glColor3f(0.2, 1, 0.2)  # Green - good
        elif flow_efficiency >= 40:
            glColor3f(1, 0.9, 0.2)  # Yellow - moderate
        else:
            glColor3f(1, 0.3, 0.2)  # Red - poor
        draw_text(stats_x, y_offset, f"Flow Efficiency: {flow_efficiency:.0f}%", GLUT_BITMAP_HELVETICA_12)

        # Alert messages
        current_time = time.time()
        alert_y = 220
        for msg, t in alert_messages:
            if current_time - t < 5:
                alpha = 1 - (current_time - t) / 5
                glColor3f(1, 0.3 + 0.4 * alpha, 0.3)
                draw_text(WINDOW_W - 320, alert_y, msg, GLUT_BITMAP_HELVETICA_12)
                alert_y -= 18

    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)


# =============================================================================
# INITIALIZATION FUNCTIONS
# =============================================================================

# Global intersection controllers
intersection_controllers = []


def initialize_traffic_lights():
    """Initialize traffic lights at intersections with realistic control"""
    global traffic_lights, intersection_controllers
    traffic_lights = []
    intersection_controllers = []

    intersection_id = 0
    for row in range(len(CITY_LAYOUT)):
        for col in range(len(CITY_LAYOUT[0])):
            if CITY_LAYOUT[row][col] == 1:
                # Count roads around this tile
                roads_around = 0
                has_north = row > 0 and CITY_LAYOUT[row - 1][col] == 1
                has_south = (
                    row < len(CITY_LAYOUT) - 1 and CITY_LAYOUT[row + 1][col] == 1
                )
                has_west = col > 0 and CITY_LAYOUT[row][col - 1] == 1
                has_east = (
                    col < len(CITY_LAYOUT[0]) - 1 and CITY_LAYOUT[row][col + 1] == 1
                )

                if has_north:
                    roads_around += 1
                if has_south:
                    roads_around += 1
                if has_west:
                    roads_around += 1
                if has_east:
                    roads_around += 1

                # Place intersection controller at 4-way intersections
                if roads_around >= 4:
                    x = col * TILE_SIZE + TILE_SIZE / 2
                    y = row * TILE_SIZE + TILE_SIZE / 2

                    # Create intersection controller
                    controller = IntersectionController(x, y, intersection_id)

                    # Alternate initial phases for adjacent intersections (green wave coordination)
                    # This ensures that when driving on one road, you encounter alternating signals
                    # Offset timers for more realistic traffic flow
                    row_idx = row // BLOCK_SIZE
                    col_idx = col // BLOCK_SIZE

                    # Use row+col to create proper alternation along each road
                    if (row_idx + col_idx) % 2 == 0:
                        controller.current_phase = "NS_GREEN"
                        controller.ns_state = "GREEN"
                        controller.ew_state = "RED"
                    else:
                        controller.current_phase = "EW_GREEN"
                        controller.ns_state = "RED"
                        controller.ew_state = "GREEN"

                    # Offset the timer for staggered light changes (green wave effect)
                    # This prevents all lights from changing at exactly the same time
                    timer_offset = ((row_idx * 3) + (col_idx * 2)) % 5
                    controller.timer = time.time() - timer_offset

                    intersection_controllers.append(controller)

                    # Create legacy traffic light for compatibility
                    tl = TrafficLight(x, y)
                    tl.controller = controller
                    traffic_lights.append(tl)

                    intersection_id += 1


def reset_simulation():
    """Reset the simulation"""
    global vehicles, traffic_lights, accidents, alert_messages
    global rain_particles, weather_raining, weather_fog
    global selected_vehicle_index, game_state, player_lives
    global violation_detected, has_deducted_life, sim_running
    global pedestrians, potholes, player_crashed, last_life_loss_time
    global last_random_accident_time

    vehicles.clear()
    traffic_lights.clear()
    accidents.clear()
    alert_messages.clear()
    rain_particles.clear()
    pedestrians.clear()
    potholes.clear()
    weather_raining = False
    weather_fog = False
    selected_vehicle_index = 0
    game_state = "START_SCREEN"
    player_lives = 20  # Increased from 5
    violation_detected = False
    has_deducted_life = False
    sim_running = True
    player_crashed = False
    last_life_loss_time = 0.0
    last_random_accident_time = time.time()

    add_alert("Simulation RESET")


def ensure_pedestrians():
    """Spawn pedestrians on footpaths near player"""
    if not vehicles:
        return

    player = vehicles[0]

    # Remove pedestrians that are too far from player
    pedestrians[:] = [p for p in pedestrians if
                      math.sqrt((p.x - player.x)**2 + (p.y - player.y)**2) < 600]

    # Get valid footpath positions near player
    if len(pedestrians) < MAX_PEDESTRIANS:
        footpath_positions = get_footpath_positions_near(player.x, player.y, radius=400)

        attempts = 0
        while len(pedestrians) < MAX_PEDESTRIANS and attempts < 50:
            attempts += 1

            if not footpath_positions:
                break

            # Pick a random footpath position
            base_x, base_y = random.choice(footpath_positions)

            # Add some randomness within the footpath
            px = base_x + random.uniform(-FOOTPATH_WIDTH, FOOTPATH_WIDTH)
            py = base_y + random.uniform(-FOOTPATH_WIDTH, FOOTPATH_WIDTH)

            # Verify it's on footpath and not too close to player
            dist_to_player = math.sqrt((px - player.x)**2 + (py - player.y)**2)
            if dist_to_player > 100 and is_footpath_position(px, py):
                pedestrians.append(Pedestrian(px, py))


def ensure_potholes():
    """Spawn potholes on 5% of road tiles at game start"""
    # Only spawn once at game start (when potholes list is empty)
    if len(potholes) > 0:
        return

    if not vehicles:
        return

    player = vehicles[0]

    # Go through all road tiles and spawn potholes on 5% of them
    for row in range(len(CITY_LAYOUT)):
        for col in range(len(CITY_LAYOUT[0])):
            if CITY_LAYOUT[row][col] == 1:  # Is a road tile
                # 5% chance to spawn pothole on this road tile
                if random.random() < POTHOLE_COVERAGE_RATE:
                    # Random position within the road tile
                    px = col * TILE_SIZE + random.uniform(TILE_SIZE * 0.2, TILE_SIZE * 0.8)
                    py = row * TILE_SIZE + random.uniform(TILE_SIZE * 0.2, TILE_SIZE * 0.8)

                    # Not too close to player spawn position
                    dist_to_player = math.sqrt((px - player.x)**2 + (py - player.y)**2)
                    if dist_to_player < 150:
                        continue

                    potholes.append(Pothole(px, py, radius=random.uniform(8, 15)))  # Smaller potholes


def random_accident_chance():
    """Chance for random accident to occur (from member3)"""
    global last_random_accident_time

    if not vehicles:
        return

    now = time.time()

    # Grace period at start
    if (now - start_time) < 30.0:
        return

    if now - last_random_accident_time < RANDOM_ACCIDENT_COOLDOWN:
        return

    # Base chance, doubled in rain
    chance = RANDOM_ACCIDENT_BASE_CHANCE * (2.0 if weather_raining else 1.0)

    if random.random() < chance:
        player = vehicles[0]
        # Random position near player
        rx = player.x + random.uniform(-300, 300)
        ry = player.y + random.uniform(-300, 300)

        # Keep on road
        if is_position_on_road(rx, ry):
            accidents.append({
                'x': rx,
                'y': ry,
                'time': now,
                'reason': 'RANDOM ACCIDENT'
            })
            road_blocks.append({
                'x': rx,
                'y': ry,
                'time': now
            })
            last_random_accident_time = now
            add_alert("Random accident occurred nearby!")


def cycle_vehicle_view():
    """Cycle through vehicles in THIRD_PERSON or FIRST_PERSON mode"""
    global selected_vehicle_index
    if not vehicles:
        return

    start_index = selected_vehicle_index
    while True:
        selected_vehicle_index = (selected_vehicle_index + 1) % len(vehicles)
        if not vehicles[selected_vehicle_index].crashed:
            break
        if selected_vehicle_index == start_index:
            break

    v = vehicles[selected_vehicle_index]
    if v.is_player:
        v_type = "PLAYER"
    else:
        v_type = "AI"

    speed_info = f"Speed: {v.speed:.1f}"
    add_alert(f"Now following: {v_type} Car #{selected_vehicle_index} ({speed_info})")


def init_rain():
    """Initialize rain particles"""
    global rain_particles
    rain_particles = []
    for _ in range(MAX_RAIN):
        rx = random.uniform(0, len(CITY_LAYOUT[0]) * TILE_SIZE)
        ry = random.uniform(0, len(CITY_LAYOUT) * TILE_SIZE)
        rz = random.uniform(50, 200)
        rain_particles.append((rx, ry, rz))


# =============================================================================
# DISPLAY FUNCTION
# =============================================================================


def display():
    """Main display function"""
    global last_frame_time, time_diff

    cur = time.time()
    time_diff = cur - last_frame_time
    last_frame_time = cur

    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

    # Set up 3D projection with appropriate FOV for each view
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()

    # Adjust field of view and far plane based on view mode
    if view_mode == "FIRST_PERSON":
        fov = 90  # Wide FOV for first person immersion
        far_plane = 3000.0
    elif view_mode == "THIRD_PERSON":
        fov = 70  # Medium FOV for third person
        far_plane = 3000.0
    else:
        fov = 60  # Standard FOV for aerial view
        far_plane = 5000.0  # Need to see full city

    gluPerspective(fov, WINDOW_W / WINDOW_H, 1.0, far_plane)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()

    if game_state == "START_SCREEN":
        # Start screen view
        glClearColor(0.1, 0.1, 0.15, 1.0)
        gluLookAt(0, -200, 120, 0, 0, 20, 0, 0, 1)

        # Draw platform
        glColor3f(0.25, 0.25, 0.25)
        glBegin(GL_QUADS)
        glVertex3f(-200, -200, 0)
        glVertex3f(200, -200, 0)
        glVertex3f(200, 200, 0)
        glVertex3f(-200, 200, 0)
        glEnd()

        # Draw selectable cars
        for i in range(4):
            glPushMatrix()
            glTranslatef(-120 + i * 80, 0, 10)
            glRotatef(90, 0, 0, 1)
            glColor3fv(selection_colors[i])
            glScalef(35, 18, 12)
            glutSolidCube(1)
            glPopMatrix()

    else:
        # Game view
        if weather_fog:
            glClearColor(0.4, 0.4, 0.45, 1.0)
            glEnable(GL_FOG)
            glFogi(GL_FOG_MODE, GL_LINEAR)
            glFogfv(GL_FOG_COLOR, [0.4, 0.4, 0.45, 1.0])
            glFogf(GL_FOG_START, 100.0)
            glFogf(GL_FOG_END, 800.0)
        elif weather_raining:
            glClearColor(0.2, 0.2, 0.3, 1.0)
            glDisable(GL_FOG)
        else:
            # Day/Night cycle (from member3)
            global is_night
            elapsed = time.time() - start_time
            day_factor = (math.sin(2 * math.pi * elapsed / CYCLE_DURATION) + 1) / 2
            is_night = day_factor < 0.4

            # Interpolate sky color based on day/night
            r = 0.1 + 0.3 * day_factor
            g = 0.1 + 0.5 * day_factor
            b = 0.2 + 0.6 * day_factor
            glClearColor(r, g, b, 1.0)
            glDisable(GL_FOG)

            # Adjust ambient light for day/night
            glLightModelfv(GL_LIGHT_MODEL_AMBIENT, [day_factor * 0.3] * 3 + [1.0])

        # Camera setup based on view mode
        if view_mode == "TOP":
            # Aerial view - full city bird's eye view from directly above center
            center_x = (MAP_SIZE * TILE_SIZE) / 2
            center_y = (MAP_SIZE * TILE_SIZE) / 2
            cam_height = CAMERA_SETTINGS["TOP"]["height"]

            # Camera directly above city center, looking straight down
            gluLookAt(
                center_x,
                center_y,
                cam_height,  # Camera position (above center)
                center_x,
                center_y,
                0,  # Look at center of city at ground level
                0,
                1,
                0,  # Up vector (Y-axis)
            )

        elif view_mode == "THIRD_PERSON" and vehicles:
            # Third person view - camera behind and above the vehicle
            idx = (
                selected_vehicle_index if selected_vehicle_index < len(vehicles) else 0
            )
            v = vehicles[idx]
            rad = math.radians(v.angle)

            # Camera position: behind and above the vehicle
            cam_distance = CAMERA_SETTINGS["THIRD_PERSON"]["distance"]
            cam_height = CAMERA_SETTINGS["THIRD_PERSON"]["height"]
            look_ahead = CAMERA_SETTINGS["THIRD_PERSON"]["look_ahead"]
            look_height = CAMERA_SETTINGS["THIRD_PERSON"]["look_height"]

            # Position camera behind the vehicle
            cam_x = v.x - math.cos(rad) * cam_distance
            cam_y = v.y - math.sin(rad) * cam_distance
            cam_z = cam_height

            # Look at point slightly ahead of and above the vehicle
            look_x = v.x + math.cos(rad) * look_ahead
            look_y = v.y + math.sin(rad) * look_ahead
            look_z = look_height

            gluLookAt(cam_x, cam_y, cam_z, look_x, look_y, look_z, 0, 0, 1)

        elif view_mode == "FIRST_PERSON" and vehicles:
            # First person racing view - camera on hood looking at road ahead
            idx = (
                selected_vehicle_index if selected_vehicle_index < len(vehicles) else 0
            )
            v = vehicles[idx]
            rad = math.radians(v.angle)

            cam_height = CAMERA_SETTINGS["FIRST_PERSON"]["height"]
            forward_offset = CAMERA_SETTINGS["FIRST_PERSON"]["forward_offset"]
            look_ahead = CAMERA_SETTINGS["FIRST_PERSON"]["look_ahead"]
            look_height = CAMERA_SETTINGS["FIRST_PERSON"]["look_height"]

            # Position camera on the hood of the car, looking forward
            cam_x = v.x + math.cos(rad) * forward_offset
            cam_y = v.y + math.sin(rad) * forward_offset
            cam_z = cam_height

            # Look far down the road - this gives the racing game feel
            look_x = v.x + math.cos(rad) * look_ahead
            look_y = v.y + math.sin(rad) * look_ahead
            look_z = look_height

            gluLookAt(cam_x, cam_y, cam_z, look_x, look_y, look_z, 0, 0, 1)

        else:
            # Fallback to top view if no vehicles
            center = (MAP_SIZE * TILE_SIZE) / 2
            gluLookAt(center, center, 1800, center, center, 0, 0, 1, 0)

        # Draw city and vehicles
        draw_city()

        # Draw intersection controllers (traffic lights)
        for controller in intersection_controllers:
            controller.draw()

        # Draw vehicles with player highlight in TOP view
        for v in vehicles:
            if view_mode == "TOP":
                v.draw(highlight_player=True, aerial_view=True)
            else:
                v.draw(highlight_player=False, aerial_view=False)

        # Draw minimap
        draw_minimap()

    # Draw HUD
    draw_hud()

    glutSwapBuffers()


# =============================================================================
# UPDATE FUNCTION
# =============================================================================


def timer(value):
    """Timer callback for updates"""
    global rain_particles, last_emergency_spawn_time

    if game_state == "DRIVING" and sim_running:
        # Update vehicles (skip player movement if crashed)
        for v in vehicles:
            if v.is_player and player_crashed:
                continue  # Don't move crashed player
            v.update(vehicles, traffic_lights)

        # Update intersection controllers (traffic lights)
        for controller in intersection_controllers:
            controller.update(vehicles)

        # Emergency vehicle spawning (2% chance every 30 seconds)
        current_time = time.time()
        if current_time - last_emergency_spawn_time >= EMERGENCY_SPAWN_INTERVAL:
            if random.random() < EMERGENCY_SPAWN_CHANCE:
                spawn_emergency_vehicle()
                add_alert("EMERGENCY VEHICLE SPAWNED!")
            last_emergency_spawn_time = current_time

        # Update pedestrians (from member3)
        ensure_pedestrians()
        for ped in pedestrians:
            ped.update()

        # Ensure potholes exist (from member3)
        ensure_potholes()

        # Random accident chance (from member3)
        random_accident_chance()

        # Update rain particles
        if weather_raining and rain_particles:
            new_particles = []
            for rx, ry, rz in rain_particles:
                new_z = rz - 8
                if new_z < 0:
                    new_z = random.uniform(150, 250)
                new_particles.append((rx, ry, new_z))
            rain_particles = new_particles

        # Despawn crashed AI vehicles after 15 seconds and spawn new ones
        crashed_ai_to_remove = []
        for v in vehicles:
            if v.crashed and not v.is_player and v.crash_time > 0:
                if current_time - v.crash_time > 15.0:  # 15 seconds despawn timer
                    crashed_ai_to_remove.append(v)

        # Remove crashed vehicles and spawn new ones
        for v in crashed_ai_to_remove:
            vehicles.remove(v)
            # Spawn a replacement AI vehicle
            spawn_replacement_ai_vehicle()
            add_alert("Crashed vehicle cleared, new vehicle spawned")

        # Clean up old accidents
        for accident in accidents[:]:
            if current_time - accident["time"] > 15:  # Match despawn timer
                accidents.remove(accident)

        # Clean up old road blocks
        for block in road_blocks[:]:
            if current_time - block.get("time", current_time) > 30:
                road_blocks.remove(block)

    glutPostRedisplay()
    glutTimerFunc(16, timer, 0)


def spawn_emergency_vehicle():
    """Spawn an emergency vehicle at a random road location"""
    attempts = 0
    while attempts < 50:
        r = random.randint(1, len(CITY_LAYOUT) - 2)
        c = random.randint(1, len(CITY_LAYOUT[0]) - 2)
        if CITY_LAYOUT[r][c] == 1:
            vx = c * TILE_SIZE + TILE_SIZE / 2
            vy = r * TILE_SIZE + TILE_SIZE / 2

            # Check distance from other vehicles
            too_close = False
            for v in vehicles:
                dist = math.sqrt((vx - v.x) ** 2 + (vy - v.y) ** 2)
                if dist < 100:
                    too_close = True
                    break

            if not too_close:
                emergency = Vehicle(vx, vy, is_emergency=True)
                vehicles.append(emergency)
                return
        attempts += 1


def spawn_replacement_ai_vehicle():
    """Spawn a replacement AI vehicle at a random road location (away from player)"""
    if not vehicles:
        return

    player = vehicles[0]
    attempts = 0

    while attempts < 50:
        r = random.randint(1, len(CITY_LAYOUT) - 2)
        c = random.randint(1, len(CITY_LAYOUT[0]) - 2)
        if CITY_LAYOUT[r][c] == 1:
            vx = c * TILE_SIZE + TILE_SIZE / 2
            vy = r * TILE_SIZE + TILE_SIZE / 2

            # Check distance from player (spawn away from player's view)
            dist_to_player = math.sqrt((vx - player.x) ** 2 + (vy - player.y) ** 2)
            if dist_to_player < 300:  # Not too close to player
                attempts += 1
                continue

            # Check distance from other vehicles
            too_close = False
            for v in vehicles:
                dist = math.sqrt((vx - v.x) ** 2 + (vy - v.y) ** 2)
                if dist < 80:
                    too_close = True
                    break

            # Check not spawning on accident/road block
            blocked = False
            for accident in accidents:
                dist = math.sqrt((vx - accident['x']) ** 2 + (vy - accident['y']) ** 2)
                if dist < 100:
                    blocked = True
                    break

            if not too_close and not blocked:
                new_vehicle = Vehicle(vx, vy)
                vehicles.append(new_vehicle)
                return
        attempts += 1


# =============================================================================
# KEYBOARD CONTROLS
# =============================================================================


def keyboard(key, x, y):
    """Handle keyboard input"""
    global view_mode, sim_running, game_state, selected_vehicle_index
    global weather_raining, weather_fog, rain_particles, selected_car_color

    k = key.decode("utf-8")

    if game_state == "START_SCREEN":
        if k in ["1", "2", "3", "4"]:
            # Clear and initialize
            vehicles.clear()
            traffic_lights.clear()
            accidents.clear()
            alert_messages.clear()
            pedestrians.clear()
            potholes.clear()

            selected_car_color = int(k) - 1

            # Reset player state
            global player_crashed, last_life_loss_time, last_random_accident_time, player_lives
            player_crashed = False
            last_life_loss_time = 0.0
            last_random_accident_time = time.time()
            player_lives = 20

            # Initialize traffic lights
            initialize_traffic_lights()

            # Reset emergency spawn timer
            global last_emergency_spawn_time
            last_emergency_spawn_time = time.time()

            # Add player vehicle - spawn on a road
            # Roads are at multiples of BLOCK_SIZE (0, 5, 10, 15, 20, 25, 30, 35, 40)
            # Spawn at the first inner road intersection
            spawn_row = BLOCK_SIZE  # Row 5 is a road (5 % 5 == 0)
            spawn_col = BLOCK_SIZE  # Col 5 is a road
            player_x = spawn_col * TILE_SIZE + TILE_SIZE / 2
            player_y = spawn_row * TILE_SIZE + TILE_SIZE / 2

            # Verify spawn is on road, if not find nearest road
            if not is_position_on_road(player_x, player_y):
                player_x, player_y = get_nearest_road_position(player_x, player_y)

            vehicles.append(
                Vehicle(
                    player_x,
                    player_y,
                    is_player=True,
                    color=selection_colors[selected_car_color],
                )
            )

            # Reset key states
            global key_accel, key_brake
            key_accel = False
            key_brake = False

            # Add AI vehicles - more for larger 8x8 city
            num_ai = 40
            for i in range(num_ai):
                attempts = 0
                while attempts < 50:
                    r = random.randint(1, len(CITY_LAYOUT) - 2)
                    c = random.randint(1, len(CITY_LAYOUT[0]) - 2)
                    if CITY_LAYOUT[r][c] == 1:
                        vx = c * TILE_SIZE + TILE_SIZE / 2
                        vy = r * TILE_SIZE + TILE_SIZE / 2
                        # Don't spawn too close to player
                        dist = math.sqrt((vx - player_x) ** 2 + (vy - player_y) ** 2)
                        if dist > 150:
                            vehicles.append(Vehicle(vx, vy))
                            break
                    attempts += 1

            game_state = "DRIVING"
            selected_vehicle_index = 0
            add_alert("Simulation Started! Drive safely.")

    else:
        kl = k.lower()

        if kl == "v":
            # Cycle view modes: TOP -> THIRD_PERSON -> FIRST_PERSON -> TOP
            if view_mode == "TOP":
                view_mode = "THIRD_PERSON"
                selected_vehicle_index = 0  # Start with player
                add_alert("View: THIRD PERSON (Behind Vehicle)")
            elif view_mode == "THIRD_PERSON":
                view_mode = "FIRST_PERSON"
                add_alert("View: FIRST PERSON (Driver Seat)")
            else:
                view_mode = "TOP"
                add_alert("View: AERIAL (Top Down)")

        elif kl == "e":
            if view_mode in ["THIRD_PERSON", "FIRST_PERSON"]:
                cycle_vehicle_view()
            else:
                add_alert(
                    "Press V to switch to THIRD_PERSON or FIRST_PERSON view first"
                )

        elif k == "\r":
            if vehicles:
                vehicles[0].engine_on = not vehicles[0].engine_on
                status = "ON" if vehicles[0].engine_on else "OFF"
                add_alert(f"Engine: {status}")

        elif k == " ":
            sim_running = not sim_running
            status = "RUNNING" if sim_running else "PAUSED"
            add_alert(f"Simulation: {status}")

        elif kl == "r":
            weather_raining = not weather_raining
            if weather_raining:
                init_rain()
                add_alert("Rain: ON")
            else:
                rain_particles.clear()
                add_alert("Rain: OFF")

        elif kl == "f":
            weather_fog = not weather_fog
            status = "ON" if weather_fog else "OFF"
            add_alert(f"Fog: {status}")

        elif kl == "t":
            # Respawn/clear accident (from member3)
            clear_accident_and_resume()

        elif kl == "x":
            reset_simulation()


def special_keys(key, x, y):
    """Handle special keys (arrows, page up/down) for car control"""
    global key_accel, key_brake

    if game_state == "DRIVING" and vehicles and not player_crashed:
        v = vehicles[0]  # Player vehicle

        if key == GLUT_KEY_LEFT:
            # Steer left - smooth steering
            v.angle = (v.angle + 5) % 360
        elif key == GLUT_KEY_RIGHT:
            # Steer right - smooth steering
            v.angle = (v.angle - 5) % 360
        elif key == GLUT_KEY_UP:
            # Accelerate - immediate effect + key hold mode
            key_accel = True
            if v.engine_on:
                v.target_speed = min(v.max_speed, v.target_speed + 0.5)
        elif key == GLUT_KEY_DOWN:
            # Brake - immediate effect + key hold mode
            key_brake = True
            v.target_speed = max(0.0, v.target_speed - 0.5)
        elif key == GLUT_KEY_PAGE_UP:
            # Accelerate (boost)
            if v.engine_on:
                v.target_speed = min(v.max_speed, v.target_speed + 1.5)
        elif key == GLUT_KEY_PAGE_DOWN:
            # Hard brake
            v.target_speed = max(0, v.target_speed - 2.0)


def special_keys_up(key, x, y):
    """Handle special key release for key-hold acceleration (from member3)"""
    global key_accel, key_brake

    if key == GLUT_KEY_UP:
        key_accel = False
    elif key == GLUT_KEY_DOWN:
        key_brake = False


# =============================================================================
# MAIN
# =============================================================================


def main():
    print("=" * 60)
    print("   MEMBER 1 GAME - AUTONOMOUS CITY TRAFFIC SIMULATOR")
    print("=" * 60)
    print("\nFEATURES:")
    print("  1. Automatic route selection for AI vehicles")
    print("  2. Collision detection and avoidance")
    print("  3. Weather effects (rain/fog) on speed and safety")
    print("  4. Speed control based on traffic density")
    print("  5. Racing first person view")
    print("  6. Aerial view with player car highlighted")
    print("  7. Red-light violation detection")
    print("  8. Start / Pause / Reset simulation")
    print("\nCONTROLS:")
    print("  1-4           : Select car color at start")
    print("  LEFT/RIGHT    : Steer")
    print("  UP/DOWN (hold): Accelerate/Brake (smooth)")
    print("  PgUp/PgDn     : Accelerate/Brake (boost)")
    print("  V             : Cycle view (AERIAL -> 3RD PERSON -> 1ST PERSON)")
    print("  E             : Cycle vehicles (in 3rd/1st person view)")
    print("  Enter         : Toggle engine")
    print("  Space         : Pause/Resume")
    print("  R             : Toggle rain")
    print("  F             : Toggle fog")
    print("  T             : Respawn/Clear accident")
    print("  X             : Reset simulation")
    print("\nNEW FEATURES (from member3):")
    print("  - Day/Night cycle")
    print("  - Pedestrians (12 max)")
    print("  - Potholes (3 max)")
    print("  - 5% NPC violators (ignore signals - red dot marker)")
    print("  - Random accidents")
    print("  - 20 lives with cooldown")
    print("  - Crash recovery with T key")
    print("=" * 60)

    glutInit(sys.argv)
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB | GLUT_DEPTH)
    glutInitWindowSize(WINDOW_W, WINDOW_H)
    glutCreateWindow(b"Member 1 Game - Autonomous City Traffic Simulator")

    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)
    glEnable(GL_LIGHT1)
    glEnable(GL_COLOR_MATERIAL)
    glShadeModel(GL_SMOOTH)

    # Main light
    glLightfv(GL_LIGHT0, GL_POSITION, [500, 500, 800, 1])
    glLightfv(GL_LIGHT0, GL_AMBIENT, [0.3, 0.3, 0.35, 1])
    glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.8, 0.8, 0.75, 1])

    # Fill light
    glLightfv(GL_LIGHT1, GL_POSITION, [-200, -200, 400, 1])
    glLightfv(GL_LIGHT1, GL_DIFFUSE, [0.3, 0.3, 0.4, 1])

    glutDisplayFunc(display)
    glutKeyboardFunc(keyboard)
    glutSpecialFunc(special_keys)
    glutSpecialUpFunc(special_keys_up)  # Key release handler for smooth accel (from member3)
    glutTimerFunc(16, timer, 0)

    glutMainLoop()


if __name__ == "__main__":
    main()
