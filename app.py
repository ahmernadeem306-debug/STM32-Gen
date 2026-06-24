import streamlit as st
import re

st.set_page_config(page_title="STM32 Pro CodeGen", layout="wide", page_icon="⚡")

# ========== STM32 LL CODE DATABASE ==========
MCU_DATABASE = {
    "STM32F103C8T6": {
        "freq": "72MHz", "family": "F1",
        "clock_code": """ LL_RCC_HSE_Enable(); // Why HSE? External 8MHz crystal 50ppm accurate. HSI 1% error hota
  while(LL_RCC_HSE_IsReady()!= 1) {};
  /* PLL: 8MHz * 9 = 72MHz - Why 9? 8*9=72MHz max for F103. Datasheet RM0008 Page 74 */
  LL_RCC_PLL_ConfigDomain_SYS(LL_RCC_PLLSOURCE_HSE_DIV_1, LL_RCC_PLL_MUL_9);
  LL_RCC_PLL_Enable();
  while(LL_RCC_PLL_IsReady()!= 1) {};
  /* APB1=36MHz - Why DIV2? APB1 ka max 36MHz hai. 72/2=36MHz. Timers ko x2 milta hai */
  LL_RCC_SetAPB1Prescaler(LL_RCC_APB1_DIV_2);
  LL_RCC_SetSysClkSource(LL_RCC_SYS_CLKSOURCE_PLL);""",
        "clock_tree": "HSE 8MHz Crystal -> PLL x9 -> SYSCLK 72MHz -> AHB 72MHz -> APB1 36MHz -> APB2 72MHz",
        "includes": ["stm32f1xx_ll_bus.h", "stm32f1xx_ll_rcc.h", "stm32f1xx_ll_gpio.h", "stm32f1xx_ll_utils.h"]
    },
    "STM32F401RE": {
        "freq": "84MHz", "family": "F4",
        "clock_code": """ LL_RCC_HSI_Enable(); // Why HSI? Nucleo F401 pe crystal nahi laga hota
  while(LL_RCC_HSI_IsReady()!= 1) {};
  /* PLL: 16/8*84/2=84MHz - Why? 16MHz/8=2MHz PFD. VCO=2*84=168MHz. /2=84MHz SYSCLK */
  LL_RCC_PLL_ConfigDomain_SYS(LL_RCC_PLLSOURCE_HSI, LL_RCC_PLLM_DIV_8, 84, LL_RCC_PLLP_DIV_2);
  LL_RCC_PLL_Enable();
  while(LL_RCC_PLL_IsReady()!= 1) {};
  /* Flash 2WS - Why? 84MHz=11.9ns per cycle. Flash 30ns leta hai. 2WS=3 cycles=35.7ns OK */
  LL_FLASH_SetLatency(LL_FLASH_LATENCY_2);
  LL_RCC_SetSysClkSource(LL_RCC_SYS_CLKSOURCE_PLL);""",
        "clock_tree": "HSI 16MHz -> /8 -> *84 -> /2 = 84MHz SYSCLK. Flash Latency 2WS zaroori",
        "includes": ["stm32f4xx_ll_bus.h", "stm32f4xx_ll_rcc.h", "stm32f4xx_ll_gpio.h", "stm32f4xx_ll_utils.h"]
    }
}

def parse_pins(text):
    """Extract pins from text like 'LED on PC13, Button on PA0'"""
    pins = {}
    pattern = r'(LED|Button|Stepper|ADC|PWM|UART|DIR|STEP|Input|Output)[\s\w]*on\s+(P[A-G]\d+)'
    matches = re.findall(pattern, text, re.IGNORECASE)
    for func, pin in matches:
        pins[pin.upper()] = func
    return pins

def get_pin_info(pin):
    port = pin[1]; num = pin[2:]
    if int(num) <= 4: irq = num
    elif int(num) <= 9: irq = "9_5"
    else: irq = "15_10"
    return port, num, irq

def generate_code(mcu_name, project_desc, pins_text):
    if mcu_name not in MCU_DATABASE:
        return "Error: Sirf STM32F103C8T6 ya STM32F401RE support hai abhi", ""

    mcu = MCU_DATABASE[mcu_name]
    pins = parse_pins(pins_text)
    desc_lower = project_desc.lower()

    includes = mcu["includes"].copy()
    main_code = ""
    gpio_code = ""
    isr_code = ""
    wiring = []

    # Clock Setup
    main_code += f" {mcu['clock_code']}\n LL_Init1msTick({mcu['freq'].replace('MHz','000000')}); // Why? 1ms SysTick ke liye\n\n"

    # GPIO Setup
    bus = "AHB1_GRP1" if mcu["family"] == "F4" else "APB2_GRP1"
    for pin, func in pins.items():
        port, num, irq = get_pin_info(pin)
        gpio_code += f" LL_{bus}_EnableClock(LL_{bus}_PERIPH_GPIO{port}); // Why? Peripherals OFF hote by default. 2mA save\n"

        if "led" in func.lower() or "output" in func.lower():
            gpio_code += f""" /* {pin} Output - Why 2MHz Speed? Low freq=kam EMI. LED ke liye 50MHz zaroorat nahi */
  LL_GPIO_SetPinMode(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_MODE_OUTPUT);
  LL_GPIO_SetPinSpeed(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_SPEED_FREQ_LOW);
  LL_GPIO_SetPinOutputType(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_OUTPUT_PUSHPULL);\n"""
            wiring.append(f"LED Circuit: {pin} -> 220Ω Resistor -> LED Anode -> LED Cathode -> GND")

        elif "button" in func.lower() or "input" in func.lower():
            gpio_code += f""" /* {pin} Input Pull-up - Why Pull-up? External 10k resistor ki zaroorat nahi. Idle HIGH */
  LL_GPIO_SetPinMode(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_MODE_INPUT);
  LL_GPIO_SetPinPull(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_PULL_UP);\n"""
            wiring.append(f"Button: {pin} -> Tactile Button -> GND")

        elif "stepper" in func.lower() or "pwm" in func.lower() or "step" in func.lower() or "dir" in func.lower():
            gpio_code += f""" /* {pin} PWM/Stepper Output - Why AF? Timer direct pin control kare ga hardware se */
  LL_GPIO_SetPinMode(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_MODE_ALTERNATE);
  LL_GPIO_SetPinSpeed(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_SPEED_FREQ_HIGH);\n"""
            if "step" in func.lower():
                wiring.append(f"Stepper Driver: {pin} -> STEP pin of A4988/DRV8825")
            elif "dir" in func.lower():
                wiring.append(f"Stepper Driver: {pin} -> DIR pin of A4988/DRV8825")
            else:
                wiring.append(f"Motor Driver: {pin} -> PWM Input of L298N/BTS7960")
            includes.append(f"stm32{mcu['family'].lower()}xx_ll_tim.h")

        if "interrupt" in desc_lower and "button" in func.lower():
            apb2_bus = 'APB2_GRP1'
            gpio_code += f""" /* EXTI {num} - Why SYSCFG? GPIO ko EXTI line se connect karta hai */
  LL_{apb2_bus}_EnableClock(LL_{apb2_bus}_PERIPH_SYSCFG);
  LL_SYSCFG_SetEXTISource(LL_SYSCFG_EXTI_PORT{port}, LL_SYSCFG_EXTI_LINE{num});
  LL_EXTI_EnableIT_0_31(LL_EXTI_LINE_{num}); // Why IT? Interrupt mode enable
  LL_EXTI_EnableFallingTrig_0_31(LL_EXTI_LINE_{num}); // Why Falling? Button press = HIGH to LOW
  NVIC_SetPriority(EXTI{irq}_IRQn, 0); // Why 0? Highest priority for real-time response
  NVIC_EnableIRQ(EXTI{irq}_IRQn);\n"""
            includes.append(f"stm32{mcu['family'].lower()}xx_ll_exti.h")
            isr_code += f"""
void EXTI{irq}_IRQHandler(void) {{
  if(LL_EXTI_IsActiveFlag_0_31(LL_EXTI_LINE_{num})) {{
    LL_EXTI_ClearFlag_0_31(LL_EXTI_LINE_{num}); // Why clear? ISR dobara na chale is liye
    // Yahan counter increment ya direction toggle karo
  }}
}}"""

    # Main Logic
    if "stepper" in desc_lower:
        includes.append(f"stm32{mcu['family'].lower()}xx_ll_tim.h")
        apb1_bus = 'APB1_GRP1'
        main_logic = f""" // Stepper Motor TIM2 - 1000Hz Pulse
  LL_{apb1_bus}_EnableClock(LL_{apb1_bus}_PERIPH_TIM2);
  /* Timer Freq = 72MHz/7200=10kHz. ARR=9 -> 10kHz/10=1kHz pulse - Why 7199? (7199+1)=7200. 72M/7200=10kHz */
  LL_TIM_SetPrescaler(TIM2, 7199);
  LL_TIM_SetAutoReload(TIM2, 9); // 10kHz/10 = 1kHz = 1000 steps/sec
  LL_TIM_EnableIT_UPDATE(TIM2); // Why IT? Interrupt pe pulse bhejni hai
  LL_TIM_EnableCounter(TIM2);
  NVIC_EnableIRQ(TIM2_IRQn);

  while(1) {{ __WFI(); }} // Why WFI? CPU sleep. Sirf interrupt pe wake. Power save"""
        isr_code += """
void TIM2_IRQHandler(void) {
  if(LL_TIM_IsActiveFlag_UPDATE(TIM2)) {
    LL_TIM_ClearFlag_UPDATE(TIM2);
    // LL_GPIO_TogglePin(GPIOA, LL_GPIO_PIN_8); // STEP pin toggle - apna pin lagao
  }
}"""

    elif "counter" in desc_lower:
        includes.append(f"stm32{mcu['family'].lower()}xx_ll_tim.h")
        apb1_bus = 'APB1_GRP1'
        main_logic = f""" // 32-bit Up Counter - 1us Resolution
  LL_{apb1_bus}_EnableClock(LL_{apb1_bus}_PERIPH_TIM2);
  /* Prescaler 72-1 = 1MHz - Why 71? 72MHz/(71+1)=1MHz. Har tick = 1us */
  LL_TIM_SetPrescaler(TIM2, 71);
  LL_TIM_SetAutoReload(TIM2, 0xFFFFFFFF); // Why 0xFFFFFFFF? 32-bit max. 71min tak count
  LL_TIM_EnableCounter(TIM2);

  uint32_t counter_value = 0;
  while(1) {{
    counter_value = LL_TIM_GetCounter(TIM2); // Current microseconds
    LL_mDelay(1000);
  }}"""

    elif "blink" in desc_lower:
        led_pins = [p for p, f in pins.items() if "led" in f.lower()]
        if led_pins:
            port, num, _ = get_pin_info(led_pins[0])
            main_logic = f""" while(1) {{
    LL_GPIO_TogglePin(GPIO{port}, LL_GPIO_PIN_{num}); // Why LL? 1 CPU cycle. HAL=12 cycles
    LL_mDelay(500); // 500ms ON, 500ms OFF = 1Hz blink
  }}"""
    else:
        main_logic = " while(1) {\n // Apna logic yahan likho\n }"

    # Build Final Code
    final_code = f"""/*
 * Project: {project_desc}
 * MCU: {mcu_name} @ {mcu['freq']}
 * Code Generator: STM32 LL Pro
 * Why LL Drivers? 12x faster GPIO than HAL. 3x smaller flash. Industry mein yahi use hota.
 */

{chr(10).join([f'#include "{inc}"' for inc in list(dict.fromkeys(includes))])}

void SystemClock_Config(void);
void GPIO_Config(void);
{isr_code}

int main(void) {{
{main_code}
{main_logic}
}}

void GPIO_Config(void) {{
{gpio_code}}}

void SystemClock_Config(void) {{
{mcu['clock_code']}
}}
"""

    wiring_text = "\n".join([f"{i+1}. {w}" for i, w in enumerate(wiring)])
    hardware = f"""HARDWARE WIRING DIAGRAM:
{wiring_text}

CLOCK TREE:
{mcu['clock_tree']}

STM32CubeIDE Settings:
1. New Project -> {mcu_name}
2. Pinout & Configuration -> System Core -> GPIO
3. Project Manager -> Advanced Settings -> Driver Selector -> LL
4. Code Generator -> Generated files -> Generate peripheral initialization as a pair of.c/.h
"""

    return final_code, hardware

# ========== STREAMLIT APP ==========
st.title("⚡ STM32 Professional Code Generator")
st.markdown("**Controller + Project Likho → LL Code + Hardware Wiring Mil Jaye Ga**")

col1, col2 = st.columns([1,2])
with col1:
    mcu_select = st.selectbox("1. STM32 Controller", ["STM32F103C8T6", "STM32F401RE", "STM32F407VG"])
with col2: # <-- Yahan c2 se col2 kar diya. Yehi bug tha.
    project_title = st.text_input("2. Project Ka Naam", "Stepper Motor with Button Control")

st.markdown("### 3. Hardware Pins Aur Kaam")
pins_text = st.text_area("Format: LED on PC13, Button on PA0",
"LED on PC13, Button on PA0, Stepper STEP on PA8, Stepper DIR on PA9", height=80)

project_desc = st.text_area("4. Project Detail Mein Likho - Kya Banana Hai?",
"TIM2 se 1000Hz stepper pulse generate karo. Button dabao to direction change ho. Interrupt use karo. Har register config explain karo kyun use ki.", height=120)

if st.button("🚀 GENERATE COMPLETE PROJECT", type="primary", use_container_width=True):
    if pins_text and project_desc:
        with st.spinner("Professional LL code ban raha hai..."):
            code, hw = generate_code(mcu_select, project_desc, pins_text)
            st.success("✅ Code Ready! STM32CubeIDE mein paste karo")

            tab1, tab2 = st.tabs(["📄 main.c Code", "🔌 Hardware Wiring"])
            with tab1:
                st.code(code, language="c", line_numbers=True)
                st.download_button("📥 Download main.c", code, "main.c", mime="text/plain")
            with tab2:
                st.code(hw, language="text")
    else:
        st.error("Pins aur Project Description likho")

st.markdown("---")
st.caption("100% Offline | No AI Training | No HuggingFace | Rule-Based Professional Code | GitHub Ready")
