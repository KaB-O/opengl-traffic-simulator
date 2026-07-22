# 3D Traffic Simulator

A real-time 3D City Traffic Simulation built with Python and OpenGL.

### Features
- Interactive 3D environment using OpenGL/GLUT
- Player-controlled vehicle with multiple camera views (Top, Third-person, First-person)
- AI traffic vehicles and dynamic traffic lights
- Collision detection and red-light violation system
- Weather effects, day/night cycle, pedestrians, and accidents (in advanced version)
- Lives system and game-like mechanics

### Technologies
- Python
- OpenGL, GLUT, GLU
- Real-time rendering and simulation

### How to Run
```bash
pip install PyOpenGL PyOpenGL_accelerate
python traffic_simulator.py

**Controls:**

- 1-4 : Select car at start
- Arrow Keys : Drive (Left/Right to steer, Up/Down to accelerate)
- V : Change camera view
- Space : Pause/Resume
