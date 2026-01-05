from controller import Robot

# 1. إعداد الروبوت
robot = Robot()
timestep = int(robot.getBasicTimeStep())

# 2. إعداد الكاميرات
cam_floor = robot.getDevice("cam_floor")
if cam_floor: cam_floor.enable(timestep)

cam_reg = robot.getDevice("cam_reg")
if cam_reg:
    cam_reg.enable(timestep)
    cam_reg.recognitionEnable(timestep)

# 3. إعداد الحساس (Distance Sensor)
ds_front = robot.getDevice("ds_front")
if ds_front: ds_front.enable(timestep)

# 4. إعداد مفاصل الذراع والقابض
arm_motors = []
for i in range(1, 6):
    motor = robot.getDevice(f"arm{i}")
    arm_motors.append(motor)

finger_left = robot.getDevice("finger::left")
finger_right = robot.getDevice("finger::right")

def set_arm_pos(p1, p2, p3, p4, p5):
    positions = [p1, p2, p3, p4, p5]
    for i in range(5):
        if arm_motors[i]: arm_motors[i].setPosition(positions[i])

def grip(open_gate=True):
    pos = 0.025 if open_gate else 0.0
    if finger_left and finger_right:
        finger_left.setPosition(pos)
        finger_right.setPosition(pos)

# 5. إعداد العجلات
wheels = []
for name in ['wheel1', 'wheel2', 'wheel3', 'wheel4']:
    w = robot.getDevice(name)
    if w:
        w.setPosition(float('inf'))
        w.setVelocity(0.0)
    wheels.append(w)

def set_wheels_speed(left_front, right_front, left_back, right_back):
    speeds = [left_front, right_front, left_back, right_back]
    for i in range(4):
        if wheels[i]: wheels[i].setVelocity(speeds[i])

# 6. منطق تمييز الألوان
def detect_color(r, g, b):
    if r > 200 and g > 200 and b < 100: return "YELLOW"
    if r > 200 and g < 150 and b < 150: return "RED"
    if g > 200 and r < 150 and b < 150: return "GREEN"
    if b > 200 and r < 150 and g < 150: return "BLUE"
    return "GROUND"

def find_correct_cube(target_color_name):
    objects = cam_reg.getRecognitionObjects()
    for obj in objects:
        if obj.get_model() == b'CUBE':
            colors = obj.get_colors()
            detected = ""
            if colors[0] > 0.8 and colors[1] > 0.8: detected = "YELLOW"
            elif colors[0] > 0.8: detected = "RED"
            elif colors[1] > 0.8: detected = "GREEN"
            elif colors[2] > 0.8: detected = "BLUE"
            
            if detected == target_color_name:
                return obj.get_position()
    return None

# --- المتغيرات التشغيلية ---
color_sequence = []
last_color = "GROUND"
state = "SCANNING_ARRAY"
target_cube_color = ""
counter = 0 # للتحكم في توقيت الذراع

# وضعية البداية
set_arm_pos(0, -1.1, -2.5, -1.78, 0)
grip(True)

print("--- المرحلة 1: مسح المصفوفة ---")

while robot.step(timestep) != -1:
    
    # حماية عامة: إذا كان هناك عائق قريب جداً، توقف (باستثناء مرحلة الالتقاط)
    if ds_front and ds_front.getValue() < 100 and state != "PICKUP":
        set_wheels_speed(0, 0, 0, 0)
        print("عائق قريب! توقف للأمان.")
        continue

    if state == "SCANNING_ARRAY":
        set_wheels_speed(1.0, 1.0, 1.0, 1.0)
        image = cam_floor.getImageArray()
        if image:
            r, g, b = image[0][0][0], image[0][0][1], image[0][0][2]
            current = detect_color(r, g, b)
            if current != "GROUND" and current != last_color:
                color_sequence.append(current)
                print(f"تم تسجيل: {current}")
                last_color = current
            elif current == "GROUND":
                last_color = "GROUND"
        
        if len(color_sequence) == 8:
            set_wheels_speed(0, 0, 0, 0)
            target_cube_color = color_sequence[0]
            print(f"اكتمل المسح. الهدف الأول: {target_cube_color}")
            state = "SEARCH_CUBE"

    elif state == "SEARCH_CUBE":
        pos = find_correct_cube(target_cube_color)
        if pos:
            x_off, z_depth = pos[0], pos[2]
            # دوران هادئ لتوسيط المكعب
            if abs(x_off) > 0.02:
                spd = 0.4 if x_off > 0 else -0.4
                set_wheels_speed(spd, -spd, spd, -spd)
            else:
                # التحرك للأمام باتجاه المكعب
                if z_depth > 0.22: # مسافة التوقف قبل الالتقاط
                    set_wheels_speed(0.8, 0.8, 0.8, 0.8)
                else:
                    set_wheels_speed(0, 0, 0, 0)
                    print("وصلت للمكعب. ابدأ الالتقاط.")
                    state = "PICKUP"
                    counter = 0
        else:
            # دوران للبحث في المكان دون رجوع
            set_wheels_speed(0.5, -0.5, 0.5, -0.5)

    elif state == "PICKUP":
        counter += 1
        if counter == 1:
            # إنزال الذراع فوق المكعب
            set_arm_pos(0.0, 0.45, -1.15, -1.0, 0.0)
        elif counter == 50: # انتظر حتى تصل الذراع
            grip(False) # أغلق اليد
            print("تم الإمساك بالمكعب.")
        elif counter == 100:
            # رفع المكعب
            set_arm_pos(0.0, -0.5, -1.5, -1.0, 0.0)
            print("تم رفع المكعب. المهمة نجحت!")
            state = "GO_TO_WALL"
            
    elif state == "GO_TO_WALL":
        # هنا يمكنك إضافة كود التوجه للحائط (الهدف القادم)
        set_wheels_speed(0, 0, 0, 0)
        break