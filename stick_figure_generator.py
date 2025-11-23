#!/usr/bin/env python3
"""
Source: github.com/zeittresor
Dev: ollama:gpt-oss:20b

Stick‑Figure Image Generator

Create Test Images to test own tools.

Each image contains:

* a stick‑figure on the left (black background, red joints, limb segments
  in unique colours that are fixed across all images),
* the image number on the right (if enabled).

"""

import os
import math
import random
import threading
import queue
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise RuntimeError("Pillow is required – install it with `pip install pillow`.")

# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #

def polar_vector(length: float, angle_rad: float) -> tuple[float, float]:
    """Return a vector of given length and polar angle (rad)."""
    return length * math.sin(angle_rad), length * math.cos(angle_rad)


def compute_skeleton(hip_x: int,
                     hip_y: int,
                     lengths: dict,
                     angles: dict) -> dict:
    """
    Compute the joint coordinates of a stick figure.

    Parameters
    ----------
    hip_x, hip_y : int
        Central hip coordinate.
    lengths : dict
        Lengths of all body segments.
    angles : dict
        Joint angles (rad) – angles are measured from the vertical axis.
    """
    # Base joints
    hip_center = (hip_x, hip_y)
    left_hip = (hip_x - lengths['hip_offset'], hip_y)
    right_hip = (hip_x + lengths['hip_offset'], hip_y)

    neck_y = hip_y - lengths['torso']
    neck_center = (hip_x, neck_y)

    shoulder_width = lengths['shoulder_width']
    shoulder_y = neck_y
    left_shoulder = (hip_x - shoulder_width, shoulder_y)
    right_shoulder = (hip_x + shoulder_width, shoulder_y)

    # Upper arms
    lu_ax, lu_ay = polar_vector(lengths['upper_arm'], angles['left_upper_arm'])
    left_elbow = (left_shoulder[0] + lu_ax, left_shoulder[1] + lu_ay)

    ru_ax, ru_ay = polar_vector(lengths['upper_arm'], angles['right_upper_arm'])
    right_elbow = (right_shoulder[0] + ru_ax, right_shoulder[1] + ru_ay)

    # Lower arms
    left_lower_abs_angle = angles['left_upper_arm'] + angles['left_lower_arm']
    lwa_ax, lwa_ay = polar_vector(lengths['lower_arm'], left_lower_abs_angle)
    left_wrist = (left_elbow[0] + lwa_ax, left_elbow[1] + lwa_ay)

    right_lower_abs_angle = angles['right_upper_arm'] + angles['right_lower_arm']
    rla_ax, rla_ay = polar_vector(lengths['lower_arm'], right_lower_abs_angle)
    right_wrist = (right_elbow[0] + rla_ax, right_elbow[1] + rla_ay)

    # Upper legs
    lu_lk_ax, lu_lk_ay = polar_vector(lengths['upper_leg'], angles['left_upper_leg'])
    left_knee = (left_hip[0] + lu_lk_ax, left_hip[1] + lu_lk_ay)

    ru_lk_ax, ru_lk_ay = polar_vector(lengths['upper_leg'], angles['right_upper_leg'])
    right_knee = (right_hip[0] + ru_lk_ax, right_hip[1] + ru_lk_ay)

    # Lower legs
    left_lower_leg_abs_angle = angles['left_upper_leg'] + angles['left_lower_leg']
    ll_ax, ll_ay = polar_vector(lengths['lower_leg'], left_lower_leg_abs_angle)
    left_ankle = (left_knee[0] + ll_ax, left_knee[1] + ll_ay)

    right_lower_leg_abs_angle = angles['right_upper_leg'] + angles['right_lower_leg']
    rl_ax, rl_ay = polar_vector(lengths['lower_leg'], right_lower_leg_abs_angle)
    right_ankle = (right_knee[0] + rl_ax, right_knee[1] + rl_ay)

    # Head centre
    head_center = (hip_x, neck_y - lengths['head_radius'])

    joints = {
        'hip_center': hip_center,
        'left_hip': left_hip,
        'right_hip': right_hip,
        'neck': neck_center,
        'head_center': head_center,
        'left_shoulder': left_shoulder,
        'right_shoulder': right_shoulder,
        'left_elbow': left_elbow,
        'right_elbow': right_elbow,
        'left_wrist': left_wrist,
        'right_wrist': right_wrist,
        'left_knee': left_knee,
        'right_knee': right_knee,
        'left_ankle': left_ankle,
        'right_ankle': right_ankle
    }

    return joints


# --------------------------------------------------------------------------- #
# Main application class
# --------------------------------------------------------------------------- #

class StickFigureApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Stick‑Figure Image Generator")
        self.queue = queue.Queue()
        self.total_images = 0
        self.setup_ui()

    # ----------------------------------------------------------------------- #
    # GUI layout
    # ----------------------------------------------------------------------- #

    def setup_ui(self):
        frm = ttk.Frame(self.root, padding="10")
        frm.grid(row=0, column=0, sticky="ew")

        ttk.Label(frm, text="Number of images:").grid(row=0, column=0, sticky="w")
        self.num_var = tk.StringVar(value="150")
        self.num_entry = ttk.Entry(frm, width=10, textvariable=self.num_var)
        self.num_entry.grid(row=0, column=1, sticky="w")

        self.show_numbers_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm,
                        text="Show image numbers",
                        variable=self.show_numbers_var).grid(row=1, column=0, columnspan=2, sticky="w")

        self.show_progress_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm,
                        text="Show progress bar",
                        variable=self.show_progress_var).grid(row=2, column=0, columnspan=2, sticky="w")

        self.gen_btn = ttk.Button(frm, text="Generate", command=self.start_generation)
        self.gen_btn.grid(row=3, column=0, columnspan=2, pady=(10, 0))

        self.progress = ttk.Progressbar(self.root, orient="horizontal", mode="determinate")
        self.progress.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        self.progress.grid_remove()

        self.status_var = tk.StringVar()
        self.status_lbl = ttk.Label(self.root, textvariable=self.status_var)
        self.status_lbl.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

    # ----------------------------------------------------------------------- #
    # Start generation
    # ----------------------------------------------------------------------- #

    def start_generation(self):
        try:
            num = int(self.num_var.get())
            if num <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid input", "Please enter a positive integer.")
            return

        self.gen_btn.config(state="disabled")
        self.status_var.set(f"Generating {num} images…")
        self.total_images = num

        if self.show_progress_var.get():
            self.progress['maximum'] = num
            self.progress['value'] = 0
            self.progress.grid()
        else:
            self.progress.grid_remove()

        thread = threading.Thread(target=self.generate_images, args=(num,))
        thread.daemon = True
        thread.start()

        self.root.after(100, self.process_queue)

    # ----------------------------------------------------------------------- #
    # Background image generation
    # ----------------------------------------------------------------------- #

    def generate_images(self, num_images: int):
        """
        Generate `num_images` stick‑figure PNGs and communicate progress via a queue.
        """
        out_dir = "generated_images"
        os.makedirs(out_dir, exist_ok=True)

        # Fixed colour mapping for extremities – stays the same for every image
        extremity_colors = {
            'left_upper_arm':   (255, 165, 0),   # orange
            'left_lower_arm':   (255, 255, 0),   # yellow
            'right_upper_arm':  (128, 0, 128),   # purple
            'right_lower_arm':  (0, 255, 255),   # cyan
            'left_upper_leg':   (0, 0, 255),     # blue
            'left_lower_leg':   (0, 255, 0),     # green
            'right_upper_leg':  (255, 105, 180), # hot pink
            'right_lower_leg':  (255, 0, 255)    # magenta
        }

        # Common drawing constants
        joint_color = (255, 0, 0)      # red
        torso_color = (128, 128, 128)  # gray
        head_color = (255, 255, 255)   # white
        segment_width = 8
        joint_radius = 6

        # Skeleton size parameters
        lengths = {
            'torso': 120,
            'upper_arm': 80,
            'lower_arm': 70,
            'upper_leg': 110,
            'lower_leg': 100,
            'head_radius': 50,
            'shoulder_width': 30,
            'hip_offset': 30
        }

        # Try to load a decent TrueType font for the number
        font = None
        font_candidates = [
            "DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/Library/Fonts/Arial.ttf",
            "arial.ttf",
        ]
        for path in font_candidates:
            try:
                font = ImageFont.truetype(path, 200)
                break
            except OSError:
                continue
        if font is None:
            font = ImageFont.load_default()

        # Base position of the figure (left side of the canvas)
        hip_x = 200
        hip_y = 500

        for i in range(1, num_images + 1):
            # Random limb angles (in radians)
            angles = {
                'left_upper_arm': random.uniform(-0.5, 0.5),
                'left_lower_arm': random.uniform(-0.5, 0.5),
                'right_upper_arm': random.uniform(-0.5, 0.5),
                'right_lower_arm': random.uniform(-0.5, 0.5),
                'left_upper_leg': random.uniform(-0.3, 0.3),
                'left_lower_leg': random.uniform(-0.3, 0.3),
                'right_upper_leg': random.uniform(-0.3, 0.3),
                'right_lower_leg': random.uniform(-0.3, 0.3)
            }

            joints = compute_skeleton(hip_x, hip_y, lengths, angles)

            img = Image.new("RGB", (1024, 1024), "black")
            draw = ImageDraw.Draw(img)

            # Torso
            draw.line([joints['hip_center'], joints['neck']],
                      fill=torso_color, width=segment_width)

            # Head
            head_c = joints['head_center']
            r = lengths['head_radius']
            draw.ellipse([head_c[0]-r, head_c[1]-r,
                          head_c[0]+r, head_c[1]+r],
                         fill=head_color, outline=head_color)

            # Limbs
            segments = [
                ('left_upper_arm', 'left_shoulder', 'left_elbow'),
                ('left_lower_arm', 'left_elbow', 'left_wrist'),
                ('right_upper_arm', 'right_shoulder', 'right_elbow'),
                ('right_lower_arm', 'right_elbow', 'right_wrist'),
                ('left_upper_leg', 'left_hip', 'left_knee'),
                ('left_lower_leg', 'left_knee', 'left_ankle'),
                ('right_upper_leg', 'right_hip', 'right_knee'),
                ('right_lower_leg', 'right_knee', 'right_ankle')
            ]

            for seg_name, start_joint, end_joint in segments:
                color = extremity_colors[seg_name]
                draw.line([joints[start_joint], joints[end_joint]],
                          fill=color, width=segment_width)

            # Joints
            for pos in joints.values():
                draw.ellipse([pos[0]-joint_radius, pos[1]-joint_radius,
                              pos[0]+joint_radius, pos[1]+joint_radius],
                              fill=joint_color, outline=joint_color)

            # Number on the right side (if enabled)
            if self.show_numbers_var.get():
                num_text = f"{i}"
                # Pillow ≥10: use textbbox; older Pillow: fallback to getsize
                try:
                    bbox = draw.textbbox((0, 0), num_text, font=font)
                    text_w = bbox[2] - bbox[0]
                    text_h = bbox[3] - bbox[1]
                except AttributeError:
                    text_w, text_h = draw.textsize(num_text, font=font)
                x = 1024 - text_w - 20
                y = (1024 - text_h) // 2
                draw.text((x, y), num_text, font=font, fill=(255, 255, 255))

            # Save image
            filename = os.path.join(out_dir, f"image_{i:04d}.png")
            img.save(filename, format="PNG")

            # Update progress
            self.queue.put(i)

        # Signal completion
        self.queue.put('DONE')

    # ----------------------------------------------------------------------- #
    # Queue processing (updates the UI)
    # ----------------------------------------------------------------------- #

    def process_queue(self):
        try:
            while True:
                item = self.queue.get_nowait()
                if item == 'DONE':
                    self.gen_btn.config(state="normal")
                    self.status_var.set("Generation completed.")
                    if self.show_progress_var.get():
                        self.progress.grid_remove()
                    return
                else:
                    current = item
                    if self.show_progress_var.get():
                        self.progress['value'] = current
                    self.status_var.set(f"Generated {current} of {self.total_images} images…")
        except queue.Empty:
            pass
        # Continue polling
        self.root.after(100, self.process_queue)


# --------------------------------------------------------------------------- #
# Run the application
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    root = tk.Tk()
    app = StickFigureApp(root)
    root.mainloop()
