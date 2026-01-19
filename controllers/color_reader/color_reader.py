from controller import Robot

# ================== الإعداد (Setup) ==================
robot = Robot()
timestep = int(robot.getBasicTimeStep())

# أجهزة الرؤية
cam_floor = robot.getDevice("cam_floor")
if cam_floor:
    cam_floor.enable(timestep)

cam_reg = robot.getDevice("cam_reg")
if cam_reg:
    cam_reg.enable(timestep)
    cam_reg.recognitionEnable(timestep)

# أجهزة الحركة
left_motor = robot.getDevice("left wheel")
right_motor = robot.getDevice("right wheel")
left_motor.setPosition(float('inf'))
right_motor.setPosition(float('inf'))
left_motor.setVelocity(0)
right_motor.setVelocity(0)

# أجهزة الذراع والملقط
arm_pitch = robot.getDevice("arm_pitch")
gripper_left = robot.getDevice("gripper_left")
gripper_right = robot.getDevice("gripper_right")
wrist_roll = robot.getDevice("wrist_roll") # تعريف المعصم للروبوت الأول

# مستشعرات الملقط
gl_sensor = robot.getDevice("gripper_left_sensor")
gr_sensor = robot.getDevice("gripper_right_sensor")
if gl_sensor: gl_sensor.enable(timestep)
if gr_sensor: gr_sensor.enable(timestep)

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
state = "SCAN_FLOOR"
colors_array = []
last_color = "GROUND"

task_index = 0
pickup_color = ""
delivery_color = ""

timer = 0

STOP_DISTANCE_CUBE = 0.075
STOP_DISTANCE_TARGET = 0.15

print("🚀 Pioneer 3-DX: نظام تعاوني ذكي (SEARCH_TARGET محسّن)")



# ================== متغيرات التسليم التعاوني ==================
handover_target = None        # الروبوت الآخر
STOP_DISTANCE_ROBOT = 0.30    # مسافة آمنة للتسليم


# ================== الحلقة الرئيسية ==================
while robot.step(timestep) != -1:
    try:
        # ------------------------------------------------
        # 1) مسح الأرضية
        # ------------------------------------------------
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
                        print(f"✅ تم تسجيل اللون: {curr}")
                        last_color = curr
                    elif curr == "GROUND":
                        last_color = "GROUND"

            if len(colors_array) >= 8:
                state = "NEXT_TARGET"

        # ------------------------------------------------
        # 2) تجهيز المهمة التالية
        # ------------------------------------------------
        elif state == "NEXT_TARGET":
            if task_index + 4 < len(colors_array):
                pickup_color = colors_array[task_index]
                delivery_color = colors_array[task_index + 4]
                print(f"\n🔄 مهمة {task_index + 1}: {pickup_color} -> {delivery_color}")
                state = "SEARCH_CUBE"
            else:
                state = "FINISHED"

        # ------------------------------------------------
        # 3) البحث عن المكعب (كما هو)
        # ------------------------------------------------
        elif state == "SEARCH_CUBE":
            objs = cam_reg.getRecognitionObjects()
            target_obj = None

            if objs:
                for o in objs:
                    if o.getModel() == "TARGET": continue
                    if get_color_name(o.getColors()) == pickup_color:
                        target_obj = o
                        break

            if target_obj:
                pos = target_obj.getPosition()
                side = pos[1]
                dist = abs(pos[2])

                if abs(side) > 0.04:
                    if side > 0:
                        set_speeds(-0.3, 0.3)
                    else:
                        set_speeds(0.3, -0.3)
                else:
                    if dist > STOP_DISTANCE_CUBE:
                        set_speeds(0.8, 0.8)
                    else:
                        set_speeds(0, 0)
                        state = "PICKUP_ACTION"
                        timer = 0
            else:
                set_speeds(0.5, -0.5)

        # ------------------------------------------------
        # 4) الالتقاط (PICKUP_ACTION) – مع فحص أمان
        # ------------------------------------------------
        elif state == "PICKUP_ACTION":
            timer += 1
        
            # 👐 فتح الملقط
            if timer == 1:
                print("👐 فتح الملقط")
                gripper_left.setPosition(0.09)
                gripper_right.setPosition(0.09)
        
            # 🔽 إنزال الذراع
            elif timer == 40:
                print("🔽 إنزال الذراع")
                arm_pitch.setPosition(0.8)   # ARM_DOWN_POS
        
            # ✊ إغلاق الملقط
            elif timer == 90:
                print("✊ إغلاق الملقط")
                gripper_left.setPosition(0.0)
                gripper_right.setPosition(0.0)
        
            # 🔍 فحص الإمساك
            elif timer == 150:
                left_f = gl_sensor.getValue()
                right_f = gr_sensor.getValue()
                max_force = max(left_f, right_f)
        
                # إمساك ناجح
                if max_force > 0.002:
                    print(f"📦 إمساك مبدئي ناجح ({max_force:.3f}) – بدء الرفع")
                    state = "LIFTING"
                    timer = 0
        
                # فشل الإمساك
                else:
                    print("⚠️ فشل الإمساك – إعادة المحاولة")
                    gripper_left.setPosition(0.09)
                    gripper_right.setPosition(0.09)
                    state = "RETRY_MOVE"
                    timer = 0
 
# ------------------------------------------------
# 5) الرفع (LIFTING) – مع فحص أثناء الرفع
# ------------------------------------------------
        elif state == "LIFTING":
            timer += 1
        
            # ✊ إبقاء الملقط مغلقاً
            gripper_left.setPosition(0.0)
            gripper_right.setPosition(0.0)
        
            # 🔼 رفع الذراع
            arm_pitch.setVelocity(0.8)
            arm_pitch.setPosition(-0.5)   # ARM_UP_POS
        
            # 🔍 فحص الأمان أثناء الرفع
            if timer > 20:
                left_f = gl_sensor.getValue()
                right_f = gr_sensor.getValue()
        
                # فقدان المكعب أثناء الرفع
                if left_f < 0.001 and right_f < 0.001:
                    print("❌ فقدان المكعب أثناء الرفع – إعادة المحاولة")
                    gripper_left.setPosition(0.09)
                    gripper_right.setPosition(0.09)
                    state = "RETRY_MOVE"
                    timer = 0
        
            # ✅ تأكيد النجاح
            if timer > 100:
                print(f"✅ تم تأكيد حمل المكعب – البحث عن الهدف {delivery_color}")
                state = "SEARCH_TARGET"
                timer = 0
        
# ------------------------------------------------
        # 6) الذهاب لمنطقة التسليم (SEARCH_TARGET)
        # ------------------------------------------------
        elif state == "SEARCH_TARGET":
            # إبقاء الذراع مرفوعاً أثناء المشي
            arm_pitch.setPosition(-0.5) 
            
            objs = cam_reg.getRecognitionObjects()
            target_obj = None

            # البحث عن منطقة اللون المستهدف
            if objs:
                for o in objs:
                    if o.getModel() == "TARGET" and get_color_name(o.getColors()) == delivery_color:
                        target_obj = o
                        break

            if target_obj:
                pos = target_obj.getPosition()
                side = pos[1]
                dist = abs(pos[2])

                # محاذاة وتوجيه
                if abs(side) > 0.05:
                    if side > 0: set_speeds(-0.25, 0.25)
                    else: set_speeds(0.25, -0.25)
                else:
                    if dist > STOP_DISTANCE_TARGET:
                        set_speeds(0.7, 0.7)
                    else:
                        # وصلنا للمنطقة المستهدفة
                        set_speeds(0, 0)
                        
                        # إذا كان هذا هو المكعب الأخير (الرابع)
                        if task_index == 3:
                            print("🤝 هذا آخر مكعب! جاري البحث عن الروبوت الشريك...")
                            state = "SEARCH_ROBOT"
                        else:
                            # مكعب عادي - ضعه على الأرض
                            state = "DROP_ACTION"
                        
                        timer = 0
            else:
                # دوران للبحث عن اللون
                set_speeds(0.4, -0.4)
        # ------------------------------------------------
        # 7) وضع المكعب
        # ------------------------------------------------
        # ------------------------------------------------
        # 7) وضع المكعب (DROP_ACTION) – محسّن مثل الروبوت الأول
        # ------------------------------------------------
        elif state == "DROP_ACTION":
            timer += 1
        
            # 🔽 إنزال الذراع لوضع المكعب
            if timer == 20:
                print("🔽 إنزال لوضع المكعب...")
                arm_pitch.setPosition(0.8)   # ARM_DOWN_POS
        
            # 👐 إفلات المكعب
            elif timer == 70:
                print("👐 إفلات...")
                gripper_left.setPosition(0.09)
                gripper_right.setPosition(0.09)
        
            # 🔼 رفع الذراع + ابتعاد
            elif timer == 100:
                print("🔼 رفع الذراع والابتعاد...")
                arm_pitch.setPosition(-0.5)  # ARM_UP_POS
                set_speeds(-0.8, -0.8)
        
            # ✅ إنهاء العملية والانتقال للمهمة التالية
            elif timer == 150:
                set_speeds(0, 0)
                task_index += 1
                print(f"📦 تم تسليم المكعب رقم {task_index}")
                state = "NEXT_TARGET"
                timer = 0


        elif state == "RETRY_MOVE":
            set_speeds(-1.0, -1.0)
            arm_pitch.setPosition(-0.5)
            timer += 1
            if timer > 40:
                state = "SEARCH_CUBE"
                timer = 0

        elif state == "FINISHED":
            set_speeds(0, 0)
# ================================================================
# القسم المدمج: البحث، التتبع، وتعديل الوضعية للتسليم (Handover)
# ================================================================
        
        elif state == "SEARCH_ROBOT":
            # 1. حركة انزياح بسيطة للخلف لإفساح مجال للرؤية
            if timer < 20:
                print("roll back... إفساح المجال")
                if timer < 10:
                    set_speeds(-0.4, -1.4)
                else: 
                    set_speeds(1.3, 1.3)
                timer += 0.025
                continue 
            
            # 2. تجهيز وضعية المعصم والذراع مسبقاً (من الكود الأول)
            # 1.57 تعني 90 درجة، ليصبح المكعب عمودياً (سهولة المسك للروبوت الثاني)
            if wrist_roll: wrist_roll.setPosition(1.57) 
            arm_pitch.setPosition(0.6) # وضعية مرتفعة قليلاً أثناء البحث لحماية المكعب
        
            set_speeds(0, 0)
            
            # 3. البحث عن الشريك باستخدام الكاميرا
            objs = cam_reg.getRecognitionObjects()
            handover_target = None
            
            if objs:
                for o in objs:
                    if o.getModel() == "ROBOT": 
                        handover_target = o
                        break
            
            if handover_target:
                print("👀 تم رصد الشريك - تفعيل وضعية التتبع والتسليم")
                state = "TRACK_AND_WAIT"
                timer = 0
            else:
                # دوران في المكان للبحث (من الكود الثاني)
                set_speeds(0.3, -0.3)
        
        elif state == "TRACK_AND_WAIT":
            # =======================================================
            # 🛡️ كود الحماية: التحقق من وجود المكعب
            # =======================================================
            left_f = gl_sensor.getValue()
            right_f = gr_sensor.getValue()
            
            # إذا كانت قوة الضغط ضعيفة جداً (أقل من 0.001) فهذا يعني أن المكعب سقط
            if left_f < 0.001 and right_f < 0.001:
                print("😱 تنبيه: سقط المكعب! جاري تفعيل وضع الاستعادة...")
                
                # 1. إعادة المعصم للوضع الطبيعي (الأفقي) للالتقاط
                if wrist_roll: wrist_roll.setPosition(0.0)
                
                # 2. فتح الملاقط
                gripper_left.setPosition(0.09)
                gripper_right.setPosition(0.09)
                
                # 3. العودة لحالة البحث عن المكعب
                # (سيعيد التقاطه، ثم يمر بمراحل الرفع والوصول للهدف تلقائياً حتى يعود هنا)
                state = "SEARCH_CUBE"
                timer = 0
                continue  # تخطي باقي الكود في هذه الدورة
            # =======================================================

            # 1. تحديث رؤية الهدف (الشريك) باستمرار
            objs = cam_reg.getRecognitionObjects()
            current_target = None
            
            if objs:
                for o in objs:
                    if o.getModel() == "ROBOT":
                        current_target = o
                        break
            
            if current_target:
                pos = current_target.getPosition()
                side = pos[1]       # الانحراف يمين/يسار (Lateral)
                dist = abs(pos[2])  # المسافة (Depth)
                print(f"المسافة الحالية في الروبوت الاول : {dist}")
                # 2. منطق التتبع الدوراني
                rot_speed = -side * 3.5  # معامل الحساسية
                
                if rot_speed > 0.7: rot_speed = 0.7
                elif rot_speed < -0.7: rot_speed = -0.7
                
                set_speeds(rot_speed, -rot_speed) 
                
                # 3. منطق التحكم بالذراع والمعصم (تفاعلي حسب المسافة)
                INTERACTION_DIST = 0.50 
                
                if dist < INTERACTION_DIST:
                    arm_pitch.setPosition(0.6)
                    if wrist_roll: wrist_roll.setPosition(1.57)

                    # --- منطقة التسليم ---
                    if dist < 0.378: # وسعنا النطاق قليلاً لضمان الدخول
                        set_speeds(0, 0) # ثبات تام
                        timer += 1
                        
                        if timer % 10 == 0:
                            print(f"⌛ الزميل في النطاق.. ثبات التسليم: {timer}")

                        # شرط الإفلات
                        if timer >  160: # قللنا الرقم قليلاً لتسريع العملية
                            print("👐 الروبوت الأول: إطلاق سراح المكعب (رؤية مؤكدة)!")
                            gripper_left.setPosition(0.09)
                            gripper_right.setPosition(0.09)
                            state = "FINISH_HANDOVER"
                            timer = 0
                    else:
                        # إذا ابتعد فجأة نصفر العداد
                        if timer < 30: timer = 0 
                else:
                    arm_pitch.setPosition(0.6)
                    timer = 0
            
            else:
                # =======================================================
                #  الحل الجوهري هنا: التعامل مع فقدان الرؤية اللحظي
                # =======================================================
                
                # إذا فقدنا الرؤية ولكن كنا في منتصف عملية التسليم (العداد مرتفع)
                if timer > 30: 
                    print(f"⚠️ فقدان رؤية أثناء التسليم (العداد {timer})... استمرار الإفلات!")
                    timer += 1 # استمر في العد وكأنك تراه
                    set_speeds(0, 0) # تأكد من التوقف
                    
                    # نفس شرط الإفلات الموجود بالأعلى
                    if timer > 160:
                        print("👐 الروبوت الأول: إطلاق سراح المكعب (عمياني)!")
                        gripper_left.setPosition(0.09)
                        gripper_right.setPosition(0.09)
                        state = "FINISH_HANDOVER"
                        timer = 0
                else:
                    # فقدان رؤية حقيقي (لم نكن نسلم شيئاً)
                    print("❓ فقدت الرؤية - العودة للبحث...")
                    state = "SEARCH_ROBOT"
                    timer = 20 # نعطيه وقتاً قصيراً للبحث قبل الدوران            # ------------------------------------------------
        # 11) إنهاء المهمة
        # ------------------------------------------------
        elif state == "FINISH_HANDOVER":
            timer += 1
            # الرجوع للخلف قليلاً ثم التوقف أو البحث عن مكعب جديد
            if timer < 30:
                set_speeds(-0.5, -0.5)
                arm_pitch.setPosition(-0.5) # رفع الذراع
            else:
                set_speeds(0, 0)
                print("✅ الروبوت الأول: تمت عملية التسليم.")
                # state = "SEARCH_BLOCK" # إذا أردت تكرار العملية
        # ------------------------------------------------
        # إنهاء المهمة بعد الإفلات
        # ------------------------------------------------
        elif state == "FINISH_HANDOVER":
            timer += 1
            # الرجوع للخلف قليلاً للابتعاد عن الروبوت الآخر
            set_speeds(-0.5, -0.5)
            
            if timer > 50:
                set_speeds(0, 0)
                print("🎉 تمت المهمة: الروبوت سلم المكعب وابتعد.")
                state = "FINISHED"

    except Exception as e:
        print(f"⚠️ خطأ: {e}")
        break
