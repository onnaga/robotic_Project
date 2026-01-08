from controller import Robot

# ================== الإعداد (Setup) ==================
robot = Robot()
timestep = int(robot.getBasicTimeStep())

# أجهزة الرؤية
cam_floor = robot.getDevice("cam_floor")
if cam_floor: cam_floor.enable(timestep)

cam_reg = robot.getDevice("cam_reg")
if cam_reg:
    cam_reg.enable(timestep)
    cam_reg.recognitionEnable(timestep)

# أجهزة الحركة
left_motor = robot.getDevice("left wheel")
right_motor = robot.getDevice("right wheel")
left_motor.setPosition(float('inf'))
right_motor.setPosition(float('inf'))

# أجهزة الذراع والملقط
arm_pitch = robot.getDevice("arm_pitch")
gripper_left = robot.getDevice("gripper_left")
gripper_right = robot.getDevice("gripper_right")

# مستشعرات الملقط
gl_sensor = robot.getDevice("gripper_left_sensor")
gr_sensor = robot.getDevice("gripper_right_sensor")
if gl_sensor: gl_sensor.enable(timestep)
if gr_sensor: gr_sensor.enable(timestep)

def set_speeds(l, r):
    left_motor.setVelocity(l)
    right_motor.setVelocity(r)

# ================== متغيرات التحكم ==================
state = "SCAN_FLOOR" 
colors_array = []
last_color = "GROUND"

# متغيرات المهمة الحالية
task_index = 0          # رقم المهمة الحالية (0 للمكعب الأول، 1 للثاني...)
pickup_color = ""       # لون المكعب
delivery_color = ""     # لون الهدف

pickup_timer = 0
max_x_seen = -1.0
has_reached_peak = False

# مسافة التوقف
STOP_DISTANCE = 0.075       # للمكعب
STOP_DISTANCE_TARGET = 0.15 # للهدف (أبعد قليلاً لتجنب الاصطدام)

print("🚀 Pioneer 3-DX: نظام التقاط متسلسل ذكي جاهز...")

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
                        print(f"✅ تم تسجيل اللون: {curr} (الترتيب {len(colors_array)})")
                        last_color = curr
                    elif curr == "GROUND": last_color = "GROUND"

            # ننتظر 8 ألوان (4 مكعبات + 4 أهداف)
            if len(colors_array) >= 8:
                state = "NEXT_TARGET"

        # 2) تجهيز الهدف التالي
        elif state == "NEXT_TARGET":
            # التأكد من وجود زوج (مكعب + هدف)
            if task_index + 4 < len(colors_array):
                pickup_color = colors_array[task_index]
                delivery_color = colors_array[task_index + 4]
                
                print(f"\n🔄 المهمة {task_index + 1}: مكعب {pickup_color} -> هدف {delivery_color}")
                
                # تصفير متغيرات البحث "القمة"
                has_reached_peak = False
                max_x_seen = -1.0
                state = "SEARCH_CUBE"
            else:
                print("🏁 اكتملت جميع المهام.")
                state = "FINISHED"

        # 3) البحث عن المكعب (بنفس منطق القمة)
        elif state == "SEARCH_CUBE":
            objs = cam_reg.getRecognitionObjects()
            target_obj = None
            
            if objs:
                for o in objs:
                    # نتجاهل التارجت الآن، نبحث عن المكعب فقط
                    if o.getModel() == "TARGET": continue

                    c = o.getColors()
                    det = "UNKNOWN"
                    if c[0] > 0.6 and c[1] < 0.4: det = "RED"
                    elif c[0] > 0.6 and c[1] > 0.6: det = "YELLOW"
                    elif c[1] > 0.6: det = "GREEN"
                    elif c[2] > 0.6: det = "BLUE"
                    
                    if det == pickup_color:
                        target_obj = o
                        break

            if target_obj:
                pos = target_obj.getPosition()
                z_dep = abs(pos[2])
                
                # --- خوارزمية البحث عن أعلى قيمة X (القمة) ---
                if not has_reached_peak:
                    if pos[0] >= max_x_seen:
                        max_x_seen = pos[0]
                        set_speeds(0.4, -0.4) # دوران لليسار
                    else:
                        has_reached_peak = True # وجدنا القمة، نتوقف عن الدوران
                else:
                    # التحرك نحو المكعب
                    if z_dep > STOP_DISTANCE:
                        set_speeds(0.8, 0.8)
                    else:
                        set_speeds(0, 0)
                        state = "PICKUP_ACTION"
                        pickup_timer = 0
            else:
                set_speeds(0.5, -0.5)

        # 4) عملية الالتقاط (فتح -> نزول -> إغلاق)
        elif state == "PICKUP_ACTION":
            pickup_timer += 1
            
            # فتح الأصابع وهي في الأعلى
            if pickup_timer == 1:
                gripper_left.setPosition(0.09) 
                gripper_right.setPosition(0.09)
                print("👐 فتح الأصابع...")

            # نزول الذراع
            elif pickup_timer == 40:
                arm_pitch.setPosition(0.8)
                print("🔽 نزول الذراع...")

            # إغلاق الأصابع
            elif pickup_timer == 90:
                gripper_left.setPosition(0.0) 
                gripper_right.setPosition(0.0)
                print("✊ إغلاق الأصابع...")

            # التحقق من المستشعرات
            elif pickup_timer == 150:
                if gl_sensor.getValue() > 0.002 or gr_sensor.getValue() > 0.002:
                    print(f"💎 تم الإمساك بـ {pickup_color}")
                    state = "LIFTING"
                    pickup_timer = 0
                else:
                    print("⚠️ فشل الإمساك، إعادة المحاولة...")
                    state = "RETRY_MOVE"
                    pickup_timer = 0

        # 5) التراجع وإعادة التمركز (Retry Logic)
        elif state == "RETRY_MOVE":
            pickup_timer += 1
            arm_pitch.setPosition(0.0) # رفع الذراع فوراً
            
            if pickup_timer < 50:
                set_speeds(-1.2, -1.2) # رجوع للخلف
            else:
                # تصفير المتغيرات لإعادة البحث الدقيق
                print("🔄 إعادة البحث عن المكعب...")
                has_reached_peak = False # إعادة تفعيل منطق القمة
                max_x_seen = -1.0
                set_speeds(0, 0)
                state = "SEARCH_CUBE" # العودة لحالة البحث
                pickup_timer = 0

        # 6) الرفع والتوجه للبحث عن التارجت
        elif state == "LIFTING":
            arm_pitch.setVelocity(0.5) # سرعة هادئة
            arm_pitch.setPosition(-0.5)
            
            pickup_timer += 1
            if pickup_timer > 100:
                arm_pitch.setVelocity(1.0)
                
                # الانتقال للبحث عن الهدف (Target)
                print(f"🔎 البحث عن الهدف: {delivery_color}")
                # تصفير متغيرات البحث مرة أخرى لاستخدامها مع التارجت
                has_reached_peak = False
                max_x_seen = -1.0
                state = "SEARCH_TARGET"
                pickup_timer = 0

        # 7) البحث عن الهدف (TARGET) - إضافة جديدة بنفس المنطق
        elif state == "SEARCH_TARGET":
            objs = cam_reg.getRecognitionObjects()
            target_obj = None
            
            if objs:
                for o in objs:
                    # الشرط: الموديل يجب أن يكون TARGET واللون مطابق للهدف
                    if o.getModel() == "TARGET":
                        c = o.getColors()
                        det = "UNKNOWN"
                        if c[0] > 0.6 and c[1] < 0.4: det = "RED"
                        elif c[0] > 0.6 and c[1] > 0.6: det = "YELLOW"
                        elif c[1] > 0.6: det = "GREEN"
                        elif c[2] > 0.6: det = "BLUE"
                        
                        if det == delivery_color:
                            target_obj = o
                            break
            
            if target_obj:
                pos = target_obj.getPosition()
                z_dep = abs(pos[2])
                
                # --- نفس خوارزمية القمة (Peak Search) ---
                if not has_reached_peak:
                    if pos[0] >= max_x_seen:
                        max_x_seen = pos[0]
                        set_speeds(0.4, -0.4)
                    else:
                        has_reached_peak = True
                else:
                    # التوجه نحو الهدف
                    if z_dep > STOP_DISTANCE_TARGET:
                        set_speeds(0.8, 0.8)
                    else:
                        set_speeds(0, 0)
                        state = "DROP_ACTION" # حالة وضع المكعب
                        pickup_timer = 0
            else:
                set_speeds(0.5, -0.5)

        # 8) وضع المكعب والانتهاء
        elif state == "DROP_ACTION":
            pickup_timer += 1
            
            if pickup_timer == 10:
                print("⏬ وضع المكعب...")
                gripper_left.setPosition(0.09)
                gripper_right.setPosition(0.09)
            
            elif pickup_timer == 50:
                set_speeds(-1.0, -1.0) # ابتعاد
                
            elif pickup_timer == 100:
                set_speeds(0, 0)
                task_index += 1 # الانتقال للمهمة التالية
                state = "NEXT_TARGET"
                pickup_timer = 0

        elif state == "FINISHED":
            set_speeds(0, 0)

    except Exception as e:
        print(f"⚠️ خطأ: {e}")
        break