from controller import Robot
import random

# ================== الإعداد (Setup) ==================
robot = Robot()
timestep = int(robot.getBasicTimeStep())

# 1. أجهزة الرؤية
cam_reg = robot.getDevice("cam_reg")
if cam_reg:
    cam_reg.enable(timestep)
    cam_reg.recognitionEnable(timestep)



# إضافة الكاميرا العلوية
top_cam = robot.getDevice("partner_cam") # الاسم الذي اخترته
if top_cam:
    top_cam.enable(timestep)
    top_cam.recognitionEnable(timestep)
else:
    print("⚠️ تحذير: لم يتم العثور على الكاميرا العلوية المسمى 'Camera'")
# 2. أجهزة الحركة
left_motor = robot.getDevice("left wheel")
right_motor = robot.getDevice("right wheel")
left_motor.setPosition(float('inf'))
right_motor.setPosition(float('inf'))
left_motor.setAvailableTorque(10.0) # زيادة العزم المتاح
right_motor.setAvailableTorque(10.0)
left_motor.setVelocity(0.0)
right_motor.setVelocity(0.0)



HANDOVER_STOP_DIST = 0.30  # متر (تُضبط بالتجربة)
HANDOVER_ARM_DELAY = 25   # عدد خطوات قبل إنزال الذراع

# 3. الذراع والملقط
wrist_roll = robot.getDevice("wrist_roll")
delivered_cubes = 0

arm_pitch = robot.getDevice("arm_pitch")
gripper_left = robot.getDevice("gripper_left")
gripper_right = robot.getDevice("gripper_right")

# 4. مستشعرات الملقط
gl_sensor = robot.getDevice("gripper_left_sensor")
gr_sensor = robot.getDevice("gripper_right_sensor")
if gl_sensor: gl_sensor.enable(timestep)
if gr_sensor: gr_sensor.enable(timestep)

# 5. حساسات السونار (للحماية من الروبوتات الأخرى)# 5. حساسات السونار - محاولة تعريف محسنة
ps_sensors = []
failTrys = 0 
print("🔍 جاري البحث عن الحساسات...")

# محاولة الحصول على الحساسات بالأسماء القياسية
for i in range(1,7):
    sensor_name = f'so{i}'
    sensor = robot.getDevice(sensor_name)
    if sensor:
        sensor.enable(timestep)
        ps_sensors.append(sensor)
        print(f"✅ تم العثور على الحساس وتفعيله: {sensor_name}")
    else:
        # إذا لم يجد 'so', قد تكون الأسماء 'ps' أو 'distance sensor'
        alt_name = f'ps{i}'
        sensor = robot.getDevice(alt_name)
        if sensor:
            sensor.enable(timestep)
            ps_sensors.append(sensor)
            print(f"✅ تم العثور على حساس بديل: {alt_name}")

if not ps_sensors:
    print("❌ خطأ حرج: لم يتم العثور على أي حساسات مسافة! تأكد من أسماء الحساسات في شجرة الروبوت (Scene Tree).")
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
is_aerial_target = False  # متغير جديد: هل الهدف مرفوع في الهواء؟
previous_state = ""  # متغير لحفظ الحالة قبل الهروب
pickup_color = ""        
delivery_color = ""      
# ➕ (إضافة جديدة) مصفوفة لحفظ الألوان التي تم نقلها
delivered_colors_list = []
timer = 0
has_reached_peak = False # (لم نعد نستخدمها ولكن تركتها للتوافق)

# مسافات التوقف
STOP_DISTANCE_CUBE = 0.075        
STOP_DISTANCE_TARGET = 0.15 

# وضعيات الذراع
ARM_UP_POS = -1.5    
ARM_DOWN_POS = 0.8   

# القوة
WALL_FORCE_LIMIT = 5.0 

print("🚀 Pioneer 3-DX2: جاهز (تتبع ذكي + تفادي روبوتات)...")
arm_pitch.setPosition(ARM_UP_POS)

while robot.step(timestep) != -1:
    try:
# ====================================================
        # 🚨 نظام الحماية المعتمد على القيم (800+ = خطر)
        # ====================================================
        obstacle_detected = False
        
        # نفحص الحساسات فقط إذا لم نكن في وضعية الإمساك أو الإفلات الدقيقة
        if state not in ["PICKUP_ACTION", "DROP_ACTION", "AVOID_ROBOT" ,"AERIAL_PICKUP" ,"APPROACH_PARTNER" , "SEARCH_PARTNER", "HANDOVER_PREPARE"]:
            for i in range(6):
                val = ps_sensors[i].getValue()
                
                # بناءً على قراءاتك: 1000 هو اصطدام، لذا 800 هي مسافة أمان كافية
                threshold = 800.0 
                
                # استثناء: إذا كنا نبحث عن مكعب، نتجاهل الحساسات الأمامية (3 و 4) 
                # حتى لا نهرب من المكعب نفسه إلا إذا التصقنا به (950)
                if state == "SEARCH_CUBE" and i in [3, 4]:
                    threshold = 950.0 
                
                if val > threshold:
                    obstacle_detected = True
                    # print(f"🚨 خطر! الحساس so{i} قرأ {val:.2f}. تفعيل الهروب!")
                    break
        
        if obstacle_detected:
            previous_state = state
            state = "AVOID_ROBOT"
            timer = 0
            set_speeds(-1.0, -1.0) # تراجع فوري
            continue
# ====================================================
        # 🎮 آلة الحالات (State Machine) - الترتيب الصحيح
        # ====================================================

        # 0) حالة تفادي الروبوتات (يجب أن تكون أول elif بعد نظام الحماية)
# 0) حالة تفادي الروبوتات
        if state == "AVOID_ROBOT":
            timer += 1
            if timer < 40:
                set_speeds(-1.2, -1.2) # تراجع سريع للخلف
            elif timer < 80:
                set_speeds(1.0, -1.0)  # دوران حاد للابتعاد عن العائق
            else:
                print(f"✅ تم الابتعاد، العودة للحالة: {previous_state}")
                state = previous_state
                timer = 0
                set_speeds(0, 0)
        # 1) البحث العام
# 1) البحث العام (تم تعديل منطق تحديد الهدف)
# ================================================================
# تعديل: داخل SCAN_FOR_MISMATCH للتحويل إلى البحث عن الروبوت
# ================================================================
        elif state == "SCAN_FOR_MISMATCH":
            is_aerial_target = False  # المكعبات هنا أرضية
            arm_pitch.setPosition(ARM_UP_POS)
            
            # ⭐ الشرط الجديد: إذا سلمنا 3 مكعبات، نبحث عن الروبوت بدلاً من المكعبات
            if delivered_cubes >= 3:
                print("🤖 انتهت المكعبات الأرضية.. البحث عن الروبوت الشريك!")
                state = "SEARCH_PARTNER" # حالة جديدة سنضيفها
                wrist_roll.setPosition(0.0) # المعصم أفقي ليلتقط المكعب العمودي
                timer = 0
                continue # تخطي بقية الكود والانتقال للحالة التالية

            # --- (بقية كود البحث عن المكعبات كما هو دون تغيير) ---
            set_speeds(0.5, -0.5) 
            objs = cam_reg.getRecognitionObjects()
            cubes = [o for o in objs if o.getModel() != "TARGET"]
            targets = [o for o in objs if o.getModel() == "TARGET"]

            for cube in cubes:
                for target in targets:
                    c_pos = cube.getPosition()
                    t_pos = target.getPosition()
                    width_diff = abs(c_pos[1] - t_pos[1])
                    c_depth = abs(c_pos[2])
                    t_depth = abs(t_pos[2])
                    depth_gap = t_depth - c_depth

                    if 0 < depth_gap < 0.3 and width_diff < 0.08:
                        c_color = get_color_name(cube.getColors())
                        t_color = get_color_name(target.getColors())
                        
                        if c_color != t_color: 
                            pickup_color = c_color
                            delivery_color = c_color 
                            print(f"🎯 تم رصد تطابق: {c_color}")
                            state = "SEARCH_CUBE"
                            break
        # 2) التوجه للمكعب (تتبع دقيق)
        elif state == "SEARCH_CUBE":
            arm_pitch.setPosition(ARM_UP_POS)
            gripper_left.setPosition(0.09) # تأكد أن الملقط مفتوح
            gripper_right.setPosition(0.11)

            objs = cam_reg.getRecognitionObjects()
            target_obj = None
            if objs:
                for o in objs:
                    if o.getModel() != "TARGET" and get_color_name(o.getColors()) == pickup_color:
                        target_obj = o
                        break
            
            if target_obj:
                pos = target_obj.getPosition()
                side_deviation = pos[1] 
                distance_to_obj = abs(pos[2])

                # منطق المحاذاة (تصفير الانحراف)
                if abs(side_deviation) > 0.04: 
                    if side_deviation > 0:
                        set_speeds(-0.2, 0.2)
                    else:
                        set_speeds(0.2, -0.2)
                else:
                    if is_aerial_target:
                        # التقدم
                        if distance_to_obj > STOP_DISTANCE_CUBE+0.05:
                            set_speeds(0.7, 0.7)
                        else:
                            set_speeds(0, 0)
                            state = "PICKUP_ACTION"
                            timer = 0
                    else: 
                        if distance_to_obj > STOP_DISTANCE_CUBE:
                            set_speeds(0.7, 0.7)
                        else:
                            set_speeds(0, 0)
                            state = "PICKUP_ACTION"
                            timer = 0
                        
            else:
                set_speeds(0.4, -0.4) 
# 3) الالتقاط
        elif state == "PICKUP_ACTION":
            timer += 1
            if timer == 1:
                print("👐 فتح الملقط")
                gripper_left.setPosition(0.11) 
                gripper_right.setPosition(0.11)
                
            elif timer == 40:
                if is_aerial_target:
                    print("↔️ توجيه الذراع للأمام (التقاط هوائي)")
                    arm_pitch.setPosition(0.6)  # 0.6 تقريباً مستوى أفقي (عدلها حسب ارتفاع شريكك)
                else:
                    print("🔽 إنزال الذراع للأرض (التقاط أرضي)")
                    arm_pitch.setPosition(ARM_DOWN_POS) # 0.8 للأرض
            elif timer == 100: 
                print("✊ إغلاق الملقط")
                gripper_left.setPosition(0.0) 
                gripper_right.setPosition(0.0) 
            
            elif timer == 160:
                # فحص الحساسات
                left_f = gl_sensor.getValue()
                right_f = gr_sensor.getValue()
                max_force = max(left_f, right_f)

                if max_force > WALL_FORCE_LIMIT: 
                    print(f"🚨 جدار! إفلات...")
                    gripper_left.setPosition(0.11)
                    gripper_right.setPosition(0.11)
                    state = "RETRY_MOVE"
                    timer = 0
                elif left_f > 0.002 or right_f > 0.002:
                    print(f"📦 نجاح الإمساك المبدئي ({max_force:.3f})... جاري الرفع والتحقق")
                    failTrys = 0
                    state = "LIFTING"
                    timer = 0
                else:
                    print("⚠️ فشل (فراغ)...")
                    failTrys += 1
                    state = "RETRY_MOVE"
                    timer = 0
                    if failTrys > 3:
                        print("🧭 محاولات فاشلة – جعل الملقط أفقي")
                        wrist_roll.setPosition(0.0) 

        # 4) الرفع مع التحقق المستمر
        elif state == "LIFTING":
            timer += 1
            # إجبار الملقط على البقاء مغلقاً
            gripper_left.setPosition(0.0)
            gripper_right.setPosition(0.0)
            
            # رفع الذراع
            arm_pitch.setVelocity(0.8)
            arm_pitch.setPosition(ARM_UP_POS) 

            # --- التعديل الجديد: فحص الأمان أثناء الرفع ---
            if timer > 20: # ننتظر قليلاً بعد بدء الرفع للتأكد من استقرار القراءة
                left_f = gl_sensor.getValue()
                right_f = gr_sensor.getValue()
                
                # إذا فقدنا الضغط تماماً أثناء الرفع
                if left_f < 0.001 and right_f < 0.001:
                    print("❌ فقدان المكعب أثناء الرفع! إعادة المحاولة...")
                    state = "RETRY_MOVE" # أو ارجع لحالة SEARCH_CUBE مباشرة
                    timer = 0
                    # نفتح الملقط لتجنب التعليق
                    gripper_left.setPosition(0.11)
                    gripper_right.setPosition(0.11)

            # الانتقار حتى ترتفع الذراع تماماً
            if timer > 100: 
                print(f"✅ تم التأكد من وجود المكعب. البحث عن الهدف {delivery_color}...")
                state = "SEARCH_TARGET"
                timer = 0
        # 5) البحث عن الهدف (تم تحديثه ليعمل مثل البحث عن المكعب)
        elif state == "SEARCH_TARGET":
            # حافظ على وضعية الحمل
            arm_pitch.setPosition(ARM_UP_POS)
            gripper_left.setPosition(0.0)
            gripper_right.setPosition(0.0)

            objs = cam_reg.getRecognitionObjects()
            target_obj = None
            if objs:
                for o in objs:
                    # نبحث عن كائن نوعه TARGET وله اللون المطلوب
                    if o.getModel() == "TARGET" and get_color_name(o.getColors()) == delivery_color:
                        target_obj = o
                        break
            
            if target_obj:
                pos = target_obj.getPosition()
                side_deviation = pos[1] # الانحراف الجانبي
                distance_to_obj = abs(pos[2])

                # نفس منطق المحاذاة الدقيق المستخدم مع المكعب
                if abs(side_deviation) > 0.05: # هامش أكبر قليلاً للهدف
                    if side_deviation > 0:
                        set_speeds(-0.25, 0.25)
                    else:
                        set_speeds(0.25, -0.25)
                else:
                    if distance_to_obj > STOP_DISTANCE_TARGET:
                        set_speeds(0.7, 0.7)
                    else:
                        set_speeds(0, 0)
                        state = "DROP_ACTION"
                        timer = 0
            else:
                set_speeds(0.4, -0.4) # دوران للبحث

        # 6) وضع المكعب
        elif state == "DROP_ACTION":
            timer += 1
            if timer == 20:
                print("🔽 إنزال لوضع المكعب...")
                arm_pitch.setPosition(ARM_DOWN_POS)
            elif timer == 70: 
                print("👐 إفلات...")
                gripper_left.setPosition(0.09)
                gripper_right.setPosition(0.09)
            elif timer == 100:
                print("🔼 ابتعاد...")
                arm_pitch.setPosition(ARM_UP_POS)
                set_speeds(-0.8, -0.8)
            elif timer == 150:
                set_speeds(0, 0)
                delivered_cubes += 1
                
                # ➕ (إضافة جديدة) تسجيل لون المكعب الذي تم تسليمه في القائمة
                delivered_colors_list.append(delivery_color)
                print(f"📋 تم تسجيل اللون {delivery_color}. القائمة: {delivered_colors_list}")
                
                print(f"📦 تم تسليم {delivered_cubes} مكعب/مكعبات")
            
                # ⭐ الشرط المطلوب
                if delivered_cubes > 3:
                    print("🧭 إتمام المهمة – جعل الملقط عمودي")
                    wrist_roll.setPosition(1.57)  # 90 درجة
                else:
                    wrist_roll.setPosition(0.0)   # يبقى أفقيًا
            
                state = "SCAN_FOR_MISMATCH"
                timer = 0

        # 7) المحاولة مرة أخرى (عند الفشل أو الجدار)
        elif state == "RETRY_MOVE":
            timer += 1
            arm_pitch.setPosition(ARM_UP_POS)
            if timer < 50:
                set_speeds(-0.8, -0.8) # تراجع
            elif timer < 90:
                set_speeds(0.6, -0.6) # دوران لتغيير الزاوية
            else:
                state = "SEARCH_CUBE" # إعادة البحث
                timer = 0
                
                
                # ================================================================
# إضافة: حالات التقاط المكعب من الروبوت (Handover States)
# ================================================================
        
        # 1) البحث عن الروبوت الأول
        elif state == "SEARCH_PARTNER":
            set_speeds(0.4, -0.4) # دوران للبحث
            objs = top_cam.getRecognitionObjects()
            partner = None
            if objs:
                for o in objs:
                    if o.getModel() == "ROBOT": # البحث عن الروبوت
                        partner = o
                        break
            
            if partner:
                print(" تم رصد الشريك.. ")
    # نستخدم الكاميرا الأمامية cam_reg لضمان أننا نرى المكعب كما نرى المكعب الأرضي
                objs = cam_reg.getRecognitionObjects()
                found_cube = None
                
                # نبحث عن أي مكعب (ليس TARGET)
                for o in objs:
                    if o.getModel() != "TARGET" and o.getModel() != "ROBOT":
    # الحصول على لون المكعب الذي يحمله الشريك
                        detected_color = get_color_name(o.getColors())
                        
                        # ⚠️ الشرط: هل هذا اللون موجود في القائمة؟
                        if detected_color in delivered_colors_list:
                            continue # تخطي هذا المكعب لأنه نُقل سابقاً
                        else:
                            found_cube = o # وجدنا مكعباً جديداً
                            break                
                if found_cube:
                    c_color = get_color_name(found_cube.getColors())
                    print(f"👀 تم رصد مكعب مع الشريك بلون {c_color}.. تفعيل التتبع العادي!")
                    
                    pickup_color = c_color      # تحديد اللون للالتقاط
                    delivery_color = c_color    # تحديد لون الهدف لاحقاً
                    
                    is_aerial_target = True     # ⚠️ هام جداً: أخبرنا الروبوت أن هذا الهدف مرتفع
                    
                    state = "SEARCH_CUBE"       # ✅ ننتقل لنفس حالة تتبع المكعب الأرضي
                    timer = 0
                    set_speeds(0, 0)
# 2) الاقتراب الدقيق من الروبوت
# 2) الاقتراب الدقيق من الروبوت (دمج الكاميرا مع الحساسات)
        elif state == "APPROACH_PARTNER":
            # 1. تأكد من رفع الذراع حتى لا تشوش على الكاميرا أو الحساسات
            arm_pitch.setPosition(ARM_UP_POS) 
            
            # 2. قراءة قيم الحساسات الأمامية (so3 و so4 هما الأوسط في Pioneer)
            # ملاحظة: في كودك السابق، القيمة العالية تعني عائق قريب ( > 800 خطر)
            # الحساسات: ps_sensors[3] و ps_sensors[4]
            front_val_left = ps_sensors[3].getValue()
            front_val_right = ps_sensors[4].getValue()
            
            # نأخذ المتوسط أو الأكبر بينهما لضمان أننا نرى الجسم
            avg_dist_sensor = (front_val_left + front_val_right) / 2
            
            # 3. استخدام الكاميرا للتوجيه فقط (يمين/يسار)
            objs = top_cam.getRecognitionObjects()
            partner = None
            
            if objs:
                for o in objs:
                    if o.getModel() == "ROBOT": 
                        partner = o
                        break
            
            if partner:
                pos = partner.getPosition()
                side = pos[1] # الانحراف الجانبي (حسب تجربتك الناجحة)
                
                # --- [أ] منطق التوجيه (الكاميرا) ---
                if abs(side) > 0.04:
                    if side > 0: set_speeds(-0.2, 0.2)
                    else: set_speeds(0.2, -0.2)
                    
                # --- [ب] منطق التقدم (الحساسات) ---
                else:
                    # أنت قلت سابقاً أن 800 تعني اصطدام/خطر
                    # نريد التوقف قبل الاصطدام بقليل ولكن قريبين جداً للمصافحة
                    # جرب قيمة بين 300 إلى 500 (كلما زادت القيمة، اقترب الروبوت أكثر)
                    STOP_SENSOR_THRESHOLD = 400.0 
                    
                    print(f"📏 الحساسات: {avg_dist_sensor:.1f} | الكاميرا Side: {side:.3f}")

                    if avg_dist_sensor < STOP_SENSOR_THRESHOLD:
                        # لم نصل بعد (القيمة منخفضة = الطريق فارغ أمامنا)
                        set_speeds(0.5, 0.5)
                    else:
                        # القيمة تجاوزت الحد = نحن قريبون جداً من الروبوت الآخر
                        set_speeds(0, 0)
                        print(f"✅ توقف بالحساسات ({avg_dist_sensor:.1f}).. التجهيز للاستلام")
                        state = "HANDOVER_PREPARE"
                        timer = 0
            
            else:
                # إذا فقدنا الكاميرا ولكن الحساسات تقرأ شيئاً قريباً جداً، قد نكون وصلنا بالفعل!
                if avg_dist_sensor > 600:
                    print("⚠️ الكاميرا لا ترى، لكن الحساسات تقول أننا وصلنا!")
                    set_speeds(0, 0)
                    state = "HANDOVER_PREPARE"
                    timer = 0
                else:
                    print("🔍 بحث عن الشريك...")
                    set_speeds(0.2, -0.2) # دوران بطيء للبحث


        elif state == "HANDOVER_PREPARE":
            timer += 1
            set_speeds(0, 0)  # تثبيت التوقف
        
            if timer == 1:
                print("🛑 الآن رفع الذراع لوضعية الاستلام (0.6)")
                # ✅ الآن فقط نضع الذراع في الوضع الأفقي لأننا توقفنا ووصلنا
                arm_pitch.setPosition(0.6)  
                
                # فتح الملقط
                gripper_left.setPosition(0.09)
                gripper_right.setPosition(0.09)
        
            # ننتظر وقتاً كافياً (HANDOVER_ARM_DELAY = 25) لتستقر الذراع
            if timer > HANDOVER_ARM_DELAY:
                print("🤝 الذراع استقرت.. الانتقال للالتقاط")
                state = "AERIAL_PICKUP"
                timer = 0
        # 3) تنفيذ الالتقاط الجوي
        elif state == "AERIAL_PICKUP":
            set_speeds(0, 0)
            timer += 1
            
            # تثبيت الذراع أفقياً
            arm_pitch.setPosition(0.6)
            
            if timer == 20:
                print("✊ إغلاق الملقط على مكعب الزميل")
                gripper_left.setPosition(0.0)
                gripper_right.setPosition(0.0)
            
            elif timer == 80:
                # التحقق هل أمسكنا شيئاً؟
                l_val = gl_sensor.getValue()
                r_val = gr_sensor.getValue()
                if l_val > 0.002 or r_val > 0.002:
                    print(f"📦 نجاح الاستلام! ({max(l_val, r_val):.3f})")
                    # نفترض أن اللون هو الأحمر للمكعب الأخير أو حسب المنطق
                    delivery_color = "RED"  # أو اجعلها متغير عام إذا كنت تعرف اللون
                    state = "REVERSE_AND_DELIVER"
                else:
                    print("⚠️ فشل الاستلام (فراغ).. محاولة تقدم بسيط")
                    set_speeds(0.2, 0.2) # تقدم قليلاً
                    if timer > 100: # مهلة نهائية
                        timer = 0 # إعادة دورة الإغلاق
            
        # 4) الرجوع للخلف والذهاب للتسليم
        elif state == "REVERSE_AND_DELIVER":
            timer += 1
            # رفع الذراع للأعلى لحماية المكعب
            arm_pitch.setPosition(ARM_UP_POS)
            
            if timer < 40:
                set_speeds(-0.8, -0.8) # رجوع للخلف للانفصال عن الروبوت الأول
            else:
                print("🚚 التوجه للهدف...")
                state = "SEARCH_TARGET" # الانتقال لمنطق التسليم الموجود مسبقاً
                timer = 0

    except Exception as e:
        print(f"⚠️ Error: {e}")
        break