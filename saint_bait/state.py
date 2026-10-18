"""Shared session state; mutable values always accessed through this module."""

import threading
import time


last_cast_time, last_gb_time, last_flashlight_time, last_random_move_time = (0.0, 0.0, 0.0, 0)
is_flashlight_on, is_casting, first_run, pending_bite = (False, False, True, False)
stop_event, interrupt_event = (threading.Event(), threading.Event())
cur_rod_in_hand, last_cons_time = (None, time.time())
start_work_time = time.time()
last_interrupted_state, state, cur_idx = (0, 0, 0)
hook_performed = False
t_pull = 0.0
danger_was_triggered = False
t_dist_reached = None
spin_offset_x = 0
spin_offset_y = 0
spin_walk_offset = 0
spin_walk_keys = []
camera_history = []
cast_counter = 0
net_used = False
jig_started = False
is_spinning_mode = False
last_chat_time = 0
first_chat_sent = False
first_chat_delay = 0
chat_start_time = 0
no_line_lift_done = False
last_feed_tremor_time = 0
feed_tremor_offset_x = 0
feed_tremor_offset_y = 0
feed_tremor_history = []
feed_tremor_counter = 0
ocr_debug_active = False
ocr_debug_casting = False
ocr_debug_thread = None
ocr_live_active = False
ocr_live_casting = False
no_line_flashlight_on = False
no_line_last_flashlight_check = 0
no_line_work_start = 0
no_line_break_duration = 0
no_line_last_action_time = 0
no_line_action_cooldown = 60
