from controller import Robot

# ================== الإعداد (Setup) ==================
robot = Robot()
timestep = int(robot.getBasicTimeStep())

cam_floor = robot.getDevice("cam_floor")
if cam_floor: cam_floor.enable(timestep)

cam_reg = robot.getDevice("cam_reg")
if cam_reg:
    cam_reg.enable(timestep)
    cam_reg.recognitionEnable(timestep)

left_motor = robot.getDevice("left wheel")
right_motor = robot.getDevice("right wheel")
left_motor.setPosition(float('inf'))
right_motor.setPosition(float('inf'))
left_motor.setVelocity(0.0)
right_motor.setVelocity(0.0)

def set_speeds(l, r):
    left_motor.setVelocity(l)
    right_motor.setVelocity(r)

# ================== متغيرات التتبع والقمة ==================
state = "SCAN_FLOOR" 
colors_array = []
last_color = "GROUND"
target_color = ""

max_x_seen = -1.0
has_reached_peak = False 

# ثوابت المسافة المعدلة
STOP_DISTANCE = 0.20  # جعلناه يقترب جداً (20 سم بدلاً من 45)

print("🚀 Pioneer 3-DX: التوجه النهائي نحو الهدف...")

while robot.step(timestep) != -1:
    try:
        # 1) مسح الأرضية
        if state == "SCAN_FLOOR":
            set_speeds(2.0, 2.0)
            if cam_floor:
                img = cam_floor.getImageArray()
                if img:
                    r, g, b = img[0][0][0], img[0][0][1], img[0][0][2]
                    curr = "GROUND"
                    if r > 200 and g > 200: curr = "YELLOW"
                    elif r > 200: curr = "RED"
                    elif g > 200: curr = "GREEN"
                    elif b > 200: curr = "BLUE"
                    
                    if curr != "GROUND" and curr != last_color:
                        colors_array.append(curr)
                        print(f"✅ تم تسجيل لون الأرضية: {curr}")
                        last_color = curr
                    elif curr == "GROUND":
                        last_color = "GROUND"

            if len(colors_array) >= 8:
                set_speeds(0, 0)
                target_color = colors_array[0]
                print(f"🎯 الهدف: {target_color} | جاري البحث عن القمة...")
                state = "SEARCH_CUBE"

        # 2) البحث عن القمة والتقدم
        elif state == "SEARCH_CUBE":
            objs = cam_reg.getRecognitionObjects()
            target_obj = None

            if objs:
                for o in objs:
                    raw_colors = o.getColors()
                    if not raw_colors: continue
                    r_c, g_c, b_c = raw_colors[0], raw_colors[1], raw_colors[2]
                    det = "UNKNOWN"
                    if r_c > 0.6 and g_c < 0.4: det = "RED"
                    elif r_c > 0.6 and g_c > 0.6: det = "YELLOW"
                    elif g_c > 0.6: det = "GREEN"
                    elif b_c > 0.6: det = "BLUE"
                    if det == target_color:
                        target_obj = o
                        break

            if target_obj:
                current_x = target_obj.getPosition()[0]
                z_dep = abs(target_obj.getPosition()[2])

                # منطق القمة: إذا لم نصل للقمة بعد أو تجاوزناها للتو
                if not has_reached_peak:
                    if current_x >= max_x_seen:
                        max_x_seen = current_x
                        set_speeds(0.6, -0.6) # استمر في الدوران يميناً للبحث عن الذروة
                        print(f"📈 البحث عن القمة: {current_x:.2f}")
                    else:
                        print(f"📉 تم تجاوز القمة ({max_x_seen:.2f}). البدء في التقدم...")
                        has_reached_peak = True
                
                # إذا تم تحديد القمة، نبدأ المشي للأمام
                else:
                    if z_dep > STOP_DISTANCE:
                        set_speeds(2.5, 2.5) # سرعة أكبر للتقدم
                        print(f"⬆️ اتقدم للأمام.. المسافة المتبقية: {z_dep:.2f}")
                    else:
                        set_speeds(0, 0)
                        print(f"✅ تم الوصول النهائي والالتصاق بالهدف {target_color}")
                        state = "FINISH"
            else:
                # إذا فقد الروبوت المكعب أثناء الدوران
                set_speeds(0.5, -0.5)

        elif state == "FINISH":
            set_speeds(0, 0)

    except Exception as e:
        print(f"⚠️ خطأ: {e}")
        set_speeds(0, 0)
        break