from controller import Robot

# ================== الإعداد (Setup) ==================
robot = Robot()
timestep = int(robot.getBasicTimeStep())

# 1. تفعيل أجهزة الرؤية
cam_reg = robot.getDevice("cam_reg")
if cam_reg:
    cam_reg.enable(timestep)
    cam_reg.recognitionEnable(timestep)

# 2. تفعيل أجهزة الحركة
left_motor = robot.getDevice("left wheel")
right_motor = robot.getDevice("right wheel")
left_motor.setPosition(float('inf'))
right_motor.setPosition(float('inf'))

# 3. تفعيل الذراع والملقط
arm_pitch = robot.getDevice("arm_pitch")
gripper_left = robot.getDevice("gripper_left")
gripper_right = robot.getDevice("gripper_right")

# 4. تفعيل مستشعرات الملقط (مهم جداً لحل مشكلة الجدار)
gl_sensor = robot.getDevice("gripper_left_sensor")
gr_sensor = robot.getDevice("gripper_right_sensor")
if gl_sensor: gl_sensor.enable(timestep)
if gr_sensor: gr_sensor.enable(timestep)

# 5. تفعيل حساسات المسافة (السونار)
ps_sensors = []
for i in range(8):
    sensor_name = f'so{i}'
    sensor = robot.getDevice(sensor_name)
    if sensor:
        sensor.enable(timestep)
        ps_sensors.append(sensor)

def set_speeds(l, r):
    left_motor.setVelocity(l)
    right_motor.setVelocity(r)

def get_color_name(c):
    if c[0] > 0.6 and c[1] < 0.4: return "RED"
    elif c[0] > 0.6 and c[1] > 0.6: return "YELLOW"
    elif c[1] > 0.6: return "GREEN"
    elif c[2] > 0.6: return "BLUE"
    return "UNKNOWN"

# ================== متغيرات التحكم ==================
state = "SCAN_FOR_MISMATCH"
pickup_color = ""       
delivery_color = ""     

pickup_timer = 0
max_x_seen = -1.0
has_reached_peak = False

# مسافات التوقف
STOP_DISTANCE = 0.075        
STOP_DISTANCE_TARGET = 0.15 

# وضعيات الذراع
ARM_UP_POS = -1.5   
ARM_DOWN_POS = 0.8  

# عتبة قوة الملقط (إذا زادت عنها يعني أمسكنا جداراً)
WALL_FORCE_LIMIT = 5.0 

print("🚀 Pioneer 3-DX2: جاهز مع نظام الحماية الشاملة...")

# رفع الذراع للبداية
arm_pitch.setPosition(ARM_UP_POS)

while robot.step(timestep) != -1:
    try:
        # ====================================================
        # 🛡️ أولاً: نظام الحماية الشامل (يعمل في كل الحالات)
        # ====================================================
        obstacle_detected = False
        # قراءة الحساسات الأمامية
        for sensor in ps_sensors:
            # القيمة تعتمد على المحاكاة، نفترض < 0.4 تعني قريب جداً وخطر
            if sensor.getValue() > 0.0 and sensor.getValue() < 0.45:
                obstacle_detected = True
                break
        
        # إذا وجد عائق والروبوت ليس في لحظة حرجة جداً (مثل لحظة وضع المكعب)
        # نستثني لحظة الرفع الدقيق فقط، أما الاقتراب والبحث فالحماية مفعلة
        if obstacle_detected and state not in ["PICKUP_CRITICAL_MOMENT"]:
            print(f"⛔ عائق! إعادة التموضع وإلغاء المسار الحالي...")
            
            # 1. التراجع والدوران للهروب
            set_speeds(-0.8, -0.4) 
            
            # 2. ⚠️ تصفير متغيرات القمة (هذا يضمن إعادة العملية بشكل صحيح)
            # لأن الروبوت عندما يتراجع، مساره القديم يصبح خاطئاً
            has_reached_peak = False
            max_x_seen = -1.0
            
            # 3. إذا كنا في مرحلة اقتراب، نعيد المؤقتات
            pickup_timer = 0
            
            # تخطي بقية الكود لهذا الإطار الزمني
            continue 

        # ====================================================
        # ثانياً: منطق المهمات (State Machine)
        # ====================================================
        
        # 1) البحث عن الاختلاف (Scanning)
        if state == "SCAN_FOR_MISMATCH":
            arm_pitch.setPosition(ARM_UP_POS)
            set_speeds(0.5, -0.5) 
            
            objs = cam_reg.getRecognitionObjects()
            cubes = [o for o in objs if o.getModel() != "TARGET"]
            targets = [o for o in objs if o.getModel() == "TARGET"]

            for cube in cubes:
                for target in targets:
                    c_pos = cube.getPosition()
                    t_pos = target.getPosition()
                    dist = ((c_pos[0]-t_pos[0])**2 + (c_pos[2]-t_pos[2])**2)**0.5
                    
                    if dist < 0.12: 
                        c_color = get_color_name(cube.getColors())
                        t_color = get_color_name(target.getColors())
                        
                        if c_color != t_color: 
                            pickup_color = c_color
                            delivery_color = c_color 
                            print(f"🎯 الهدف: نقل {c_color} من {t_color}")
                            
                            # تهيئة متغيرات البحث
                            has_reached_peak = False
                            max_x_seen = -1.0
                            state = "SEARCH_CUBE"
                            break

        # 2) التوجه للمكعب (مع خوارزمية القمة)
        elif state == "SEARCH_CUBE":
            arm_pitch.setPosition(ARM_UP_POS)
            objs = cam_reg.getRecognitionObjects()
            target_obj = None
            if objs:
                for o in objs:
                    if o.getModel() != "TARGET" and get_color_name(o.getColors()) == pickup_color:
                        target_obj = o
                        break
            
            if target_obj:
                pos = target_obj.getPosition()
                
                # --- خوارزمية القمة ---
                if not has_reached_peak:
                    if pos[0] >= max_x_seen:
                        max_x_seen = pos[0]
                        set_speeds(0.3, -0.3)
                    else:
                        has_reached_peak = True
                else:
                    # التحرك نحو المكعب
                    if abs(pos[2]) > STOP_DISTANCE:
                        set_speeds(0.8, 0.8)
                    else:
                        set_speeds(0, 0)
                        state = "PICKUP_ACTION"
                        pickup_timer = 0
            else:
                # دوران للبحث
                set_speeds(0.5, -0.5)

        # 3) عملية الالتقاط
        elif state == "PICKUP_ACTION":
            pickup_timer += 1
            
            if pickup_timer == 1:
                print("👐 فتح الملقط...")
                gripper_left.setPosition(0.09) 
                gripper_right.setPosition(0.09)
            elif pickup_timer == 40:
                print("🔽 إنزال الذراع...")
                arm_pitch.setPosition(ARM_DOWN_POS) 
            elif pickup_timer == 90:
                print("✊ محاولة الإمساك...")
                gripper_left.setPosition(0.0) 
                gripper_right.setPosition(0.0) 
            
            # لحظة التحقق الحاسمة
            elif pickup_timer == 150:
                left_f = gl_sensor.getValue()
                right_f = gr_sensor.getValue()
                max_force = max(left_f, right_f)

                # --- 🛑 حماية الجدار (Wall Protection) ---
                if max_force > WALL_FORCE_LIMIT: 
                    print(f"🚨 تحذير: أمسكت بجدار (القوة {max_force:.2f})! تحرير فوري...")
                    # فتح الملقط فوراً
                    gripper_left.setPosition(0.09)
                    gripper_right.setPosition(0.09)
                    # الانتقال لحالة الطوارئ
                    state = "EMERGENCY_RELEASE"
                    pickup_timer = 0
                
                # التحقق الطبيعي (مكعب)
                elif left_f > 0.002 or right_f > 0.002:
                    print(f"📦 تم الالتقاط. رفع الذراع...")
                    state = "LIFTING"
                    pickup_timer = 0
                else:
                    print("⚠️ فشل الالتقاط (فراغ). إعادة التموضع...")
                    state = "RETRY_MOVE"
                    pickup_timer = 0

        # 4) حالة الطوارئ عند الإمساك بالجدار (تمنع الانقلاب)
        elif state == "EMERGENCY_RELEASE":
            pickup_timer += 1
            arm_pitch.setPosition(ARM_UP_POS) # رفع الذراع
            
            if pickup_timer < 50:
                set_speeds(-1.0, -1.0) # تراجع سريع للخلف
            else:
                print("🔄 إعادة المحاولة بعد الخطأ...")
                has_reached_peak = False
                max_x_seen = -1.0
                state = "SEARCH_CUBE" # العودة للبحث
                pickup_timer = 0

        # 5) إعادة التموضع عند الفشل (Retry Logic)
        elif state == "RETRY_MOVE":
            pickup_timer += 1
            arm_pitch.setPosition(ARM_UP_POS)
            
            if pickup_timer < 50:
                set_speeds(-1.0, -1.0) # تراجع للخلف
            else:
                # تصفير المتغيرات لإعادة البحث الدقيق
                print("🔄 إعادة تشغيل خوارزمية البحث...")
                has_reached_peak = False 
                max_x_seen = -1.0
                state = "SEARCH_CUBE"
                pickup_timer = 0

        # 6) الرفع
        elif state == "LIFTING":
            # سرعة ورفع
            arm_pitch.setVelocity(0.8)
            arm_pitch.setPosition(ARM_UP_POS) 
            
            pickup_timer += 1
            if pickup_timer > 80:
                print(f"🚚 التوجه للهدف {delivery_color}...")
                has_reached_peak = False
                max_x_seen = -1.0
                state = "SEARCH_TARGET"
                pickup_timer = 0

        # 7) البحث عن الهدف
        elif state == "SEARCH_TARGET":
            arm_pitch.setPosition(ARM_UP_POS) 
            objs = cam_reg.getRecognitionObjects()
            target_obj = None
            if objs:
                for o in objs:
                    if o.getModel() == "TARGET" and get_color_name(o.getColors()) == delivery_color:
                        target_obj = o
                        break
            
            if target_obj:
                pos = target_obj.getPosition()
                if not has_reached_peak:
                    if pos[0] >= max_x_seen:
                        max_x_seen = pos[0]
                        set_speeds(0.3, -0.3)
                    else:
                        has_reached_peak = True
                else:
                    if abs(pos[2]) > STOP_DISTANCE_TARGET:
                        set_speeds(0.8, 0.8)
                    else:
                        set_speeds(0, 0)
                        state = "DROP_ACTION"
                        pickup_timer = 0
            else:
                set_speeds(0.5, -0.5)

        # 8) وضع المكعب
        elif state == "DROP_ACTION":
            pickup_timer += 1
            
            if pickup_timer == 10:
                print("🔽 إنزال...")
                arm_pitch.setPosition(ARM_DOWN_POS)
            
            elif pickup_timer == 50: 
                print("👐 إفلات المكعب...")
                gripper_left.setPosition(0.09)
                gripper_right.setPosition(0.09)

            elif pickup_timer == 80:
                print("🔼 رفع وابتعاد...")
                arm_pitch.setPosition(ARM_UP_POS)
                set_speeds(-1.0, -1.0)
                
            elif pickup_timer == 130:
                set_speeds(0, 0)
                state = "SCAN_FOR_MISMATCH"
                pickup_timer = 0

    except Exception as e:
        print(f"⚠️ Error: {e}")
        break