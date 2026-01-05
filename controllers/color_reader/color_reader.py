from controller import Robot

# إعدادات الروبوت
robot = Robot()
timestep = int(robot.getBasicTimeStep())

# إعداد الكاميرا
camera = robot.getDevice("cam")
camera.enable(timestep)

# إعداد المحركات
left_motor = robot.getDevice("left_motor")
right_motor = robot.getDevice("right_motor")

# ضبط المحركات لتعمل بنمط السرعة وليس الموضع
left_motor.setPosition(float('inf'))
right_motor.setPosition(float('inf'))
left_motor.setVelocity(0.0)
right_motor.setVelocity(0.0)

# قائمة لتخزين الألوان (مصفوفة الألوان الثمانية)
color_sequence = []

def detect_color(r, g, b):
    # منطق تمييز الألوان بناءً على القيم التي حصلت عليها (251, 251, 0)
    if r > 200 and g > 200 and b < 100: return "YELLOW"
    if r > 200 and g < 100 and b < 100: return "RED"
    if g > 200 and r < 100 and b < 100: return "GREEN"
    if b > 200 and r < 100 and g < 100: return "BLUE"
    return "UNKNOWN"

# متغيرات التحكم بالحركة
start_time = robot.getTime()
state = "DRIVING"
scan_count = 0

print("--- بدء عملية قراءة المصفوفة ---")

while robot.step(timestep) != -1:
    current_time = robot.getTime()
    
    if scan_count < 8:
        # الحركة للأمام قليلاً
        left_motor.setVelocity(2.0)
        right_motor.setVelocity(2.0)
        
        # بعد فترة زمنية قصيرة (تحتاج لضبطها حسب المسافة بين البلاطات)
        if current_time - start_time > 1.5:  # فرضا كل 1.5 ثانية يصل لبلاطة
            # توقف للحظة للقراءة
            left_motor.setVelocity(0.0)
            right_motor.setVelocity(0.0)
            
            # قراءة الكاميرا
            image = camera.getImageArray()
            # قراءة البكسل المركزي (بفرض أن الكاميرا 64x64)
            r = image[32][32][0]
            g = image[32][32][1]
            b = image[32][32][2]
            
            color = detect_color(r, g, b)
            color_sequence.append(color)
            
            print(f"قراءة البلاطة {scan_count + 1}: {color}")
            
            # إعادة ضبط الوقت للبلاطة التالية
            start_time = robot.getTime()
            scan_count += 1
    else:
        # التوقف التام بعد انتهاء الـ 8 بلاطات
        left_motor.setVelocity(0.0)
        right_motor.setVelocity(0.0)
        if scan_count == 8:
            print("المصفوفة النهائية التي تم قراءتها:", color_sequence)
            scan_count += 1 # لمنع تكرار الطباعة