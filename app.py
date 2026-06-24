import streamlit as st
import re

st.set_page_config(page_title="STM32 Pro CodeGen", layout="wide", page_icon="⚡")

MCU_DATABASE = {
    "STM32F103C8T6": {
        "freq": "72MHz", "family": "F1",
        "clock_code": """ LL_RCC_HSE_Enable(); // Why HSE? External 8MHz crystal 50ppm accurate
  while(LL_RCC_HSE_IsReady()!= 1) {};
  LL_RCC_PLL_ConfigDomain_SYS(LL_RCC_PLLSOURCE_HSE_DIV_1, LL_RCC_PLL_MUL_9);
  LL_RCC_PLL_Enable();
  while(LL_RCC_PLL_IsReady()!= 1) {};
  LL_RCC_SetAPB1Prescaler(LL_RCC_APB1_DIV_2); // Why DIV2? APB1 max 36MHz
  LL_RCC_SetSysClkSource(LL_RCC_SYS_CLKSOURCE_PLL);""",
        "clock_tree": "HSE 8MHz Crystal -> PLL x9 -> SYSCLK 72MHz -> AHB 72MHz -> APB1 36MHz -> APB2 72MHz",
        "includes": ["stm32f1xx_ll_bus.h", "stm32f1xx_ll_rcc.h", "stm32f1xx_ll_gpio.h", "stm32f1xx_ll_utils.h"]
    }
}

def parse_pins(text):
    pins = {}
    # FIXED: I2C, SDA, SCL, UART, TX, RX sab add kiye
    pattern = r'(LED|Button|Stepper|ADC|PWM|UART|I2C|SDA|SCL|TX|RX|DIR|STEP|Input|Output)[\s\w]*on\s+(P[A-G]\d+)'
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
    mcu = MCU_DATABASE[mcu_name]
    pins = parse_pins(pins_text)
    desc_lower = project_desc.lower()

    includes = mcu["includes"].copy()
    main_code = ""
    gpio_code = ""
    isr_code = ""
    wiring = []
    main_logic = ""

    # FIXED: GPIO_Config aur SystemClock_Config call add ki
    main_code += f" SystemClock_Config();\n GPIO_Config();\n LL_Init1msTick({mcu['freq'].replace('MHz','000000')}); // Why? 1ms SysTick\n\n"

    bus = "AHB1_GRP1" if mcu["family"] == "F4" else "APB2_GRP1"

    # GPIO + Wiring Generation
    for pin, func in pins.items():
        port, num, irq = get_pin_info(pin)
        gpio_code += f" LL_{bus}_EnableClock(LL_{bus}_PERIPH_GPIO{port});\n"

        if "led" in func.lower():
            gpio_code += f""" /* {pin} Output */
  LL_GPIO_SetPinMode(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_MODE_OUTPUT);
  LL_GPIO_SetPinSpeed(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_SPEED_FREQ_LOW);\n"""
            wiring.append(f"LED Circuit: {pin} -> 220Ω -> LED -> GND")

        elif "button" in func.lower():
            gpio_code += f""" /* {pin} Input Pull-up */
  LL_GPIO_SetPinMode(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_MODE_INPUT);
  LL_GPIO_SetPinPull(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_PULL_UP);\n"""
            wiring.append(f"Button: {pin} -> Tactile Button -> GND")

        elif "sda" in func.lower():
            gpio_code += f""" /* {pin} I2C SDA - Why AF_OD? I2C spec requires open-drain + pull-up */
  LL_GPIO_SetPinMode(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_MODE_ALTERNATE);
  LL_GPIO_SetPinSpeed(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_SPEED_FREQ_HIGH);
  LL_GPIO_SetPinOutputType(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_OUTPUT_OPENDRAIN);
  LL_GPIO_SetPinPull(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_PULL_UP);\n"""
            wiring.append(f"I2C SDA: {pin} -> MPU6050 SDA | 4.7kΩ Pull-up to 3.3V Zaroori")
            includes.append(f"stm32{mcu['family'].lower()}xx_ll_i2c.h")

        elif "scl" in func.lower():
            gpio_code += f""" /* {pin} I2C SCL - Why AF_OD? Clock line bhi open-drain */
  LL_GPIO_SetPinMode(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_MODE_ALTERNATE);
  LL_GPIO_SetPinSpeed(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_SPEED_FREQ_HIGH);
  LL_GPIO_SetPinOutputType(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_OUTPUT_OPENDRAIN);
  LL_GPIO_SetPinPull(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_PULL_UP);\n"""
            wiring.append(f"I2C SCL: {pin} -> MPU6050 SCL | 4.7kΩ Pull-up to 3.3V Zaroori")
            includes.append(f"stm32{mcu['family'].lower()}xx_ll_i2c.h")

        elif "tx" in func.lower():
            gpio_code += f""" /* {pin} UART TX - Why AF_PP? Push-pull for TX */
  LL_GPIO_SetPinMode(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_MODE_ALTERNATE);
  LL_GPIO_SetPinSpeed(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_SPEED_FREQ_HIGH);\n"""
            wiring.append(f"UART TX: {pin} -> FTDI RXD / USB-TTL RX Pin")
            includes.append(f"stm32{mcu['family'].lower()}xx_ll_usart.h")

        elif "rx" in func.lower():
            gpio_code += f""" /* {pin} UART RX - Why Input? Data receive */
  LL_GPIO_SetPinMode(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_MODE_ALTERNATE);
  LL_GPIO_SetPinPull(GPIO{port}, LL_GPIO_PIN_{num}, LL_GPIO_PULL_UP);\n"""
            wiring.append(f"UART RX: {pin} -> FTDI TXD / USB-TTL TX Pin")
            includes.append(f"stm32{mcu['family'].lower()}xx_ll_usart.h")

    # FIXED: I2C + UART Logic Ab Hamesha Chale Ga
    if "i2c" in desc_lower or "mpu6050" in desc_lower or "sda" in pins_text.lower():
        includes.append(f"stm32{mcu['family'].lower()}xx_ll_i2c.h")
        includes.append(f"stm32{mcu['family'].lower()}xx_ll_usart.h")
        main_logic = """ // I2C1 + UART1 Init
  LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_I2C1); // Why APB1? I2C1 APB1 bus pe hai
  LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_USART1); // Why APB2? USART1 APB2 pe 72MHz

  // I2C 100kHz - Why 100kHz? MPU6050 400kHz support but 100kHz stable for long wires
  LL_I2C_Disable(I2C1);
  LL_I2C_SetTiming(I2C1, 0x00201D2B); // Why 0x00201D2B? 72MHz/(1+1)*(0xD2+0xC3+2) ≈ 100kHz
  LL_I2C_Enable(I2C1);

  // UART 115200 - Why 115200? PC terminal standard. 72MHz/115200=625
  LL_USART_SetBaudRate(USART1, 72000000, LL_USART_OVERSAMPLING_16, 115200);
  LL_USART_EnableDirectionTx(USART1);
  LL_USART_Enable(USART1);

  // MPU6050 Wake Up - Why 0x6B? PWR_MGMT_1 register. Writing 0x00 wakes it up
  LL_I2C_HandleTransfer(I2C1, 0x68<<1, LL_I2C_ADDRSLAVE_7BIT, 2, LL_I2C_MODE_AUTOEND, LL_I2C_GENERATE_START_WRITE);
  while(!LL_I2C_IsActiveFlag_TXIS(I2C1)) {}; // Why wait? TX buffer ready hone tak
  LL_I2C_TransmitData8(I2C1, 0x6B);
  while(!LL_I2C_IsActiveFlag_TXIS(I2C1)) {};
  LL_I2C_TransmitData8(I2C1, 0x00);

  uint8_t data[6];
  while(1) {
    // Read Gyro XYZ from 0x43 - Why 0x43? MPU6050 datasheet GYRO_XOUT_H register
    LL_I2C_HandleTransfer(I2C1, 0x68<<1, LL_I2C_ADDRSLAVE_7BIT, 1, LL_I2C_MODE_SOFTEND, LL_I2C_GENERATE_START_WRITE);
    while(!LL_I2C_IsActiveFlag_TXIS(I2C1)) {};
    LL_I2C_TransmitData8(I2C1, 0x43);

    LL_I2C_HandleTransfer(I2C1, 0x68<<1, LL_I2C_ADDRSLAVE_7BIT, 6, LL_I2C_MODE_AUTOEND, LL_I2C_GENERATE_RESTART_READ);
    for(int i=0; i<6; i++) {
      while(!LL_I2C_IsActiveFlag_RXNE(I2C1)) {}; // Why RXNE? Data received in buffer
      data[i] = LL_I2C_ReceiveData8(I2C1);
    }

    // Send via UART - Why check TXE? TX buffer empty hona chahiye
    for(int i=0; i<6; i++) {
      while(!LL_USART_IsActiveFlag_TXE(USART1)) {};
      LL_USART_TransmitData8(USART1, data[i]);
    }
    LL_mDelay(10); // 100Hz = 10ms delay
  }"""
        wiring.append("Common GND: STM32 GND -> MPU6050 GND -> FTDI GND")
        wiring.append("Power: STM32 3.3V -> MPU6050 VCC")

    elif "uart" in desc_lower:
        includes.append(f"stm32{mcu['family'].lower()}xx_ll_usart.h")
        main_logic = """ // UART Echo 115200
  LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_USART1);
  LL_USART_SetBaudRate(USART1, 72000000, LL_USART_OVERSAMPLING_16, 115200);
  LL_USART_EnableDirectionTx(USART1);
  LL_USART_EnableDirectionRx(USART1);
  LL_USART_Enable(USART1);
  while(1) {
    if(LL_USART_IsActiveFlag_RXNE(USART1)) { // Why RXNE? Byte received
      uint8_t byte = LL_USART_ReceiveData8(USART1);
      while(!LL_USART_IsActiveFlag_TXE(USART1)) {}; // Why TXE? Wait if buffer full
      LL_USART_TransmitData8(USART1, byte); // Echo back
    }
  }"""

    else:
        main_logic = " while(1) {\n // Apna logic yahan likho\n }"

    final_code = f"""/*
 * Project: {project_desc}
 * MCU: {mcu_name} @ {mcu['freq']}
 * Code Generator: STM32 LL Pro
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
    if not wiring:
        wiring_text = "1. Pins format check karo: 'I2C SDA on PB7, UART TX on PA9'"

    hardware = f"""HARDWARE WIRING DIAGRAM:
{wiring_text}

CLOCK TREE:
{mcu['clock_tree']}

STM32CubeIDE Settings:
1. New Project -> {mcu_name}
2. Pinout & Configuration -> System Core -> GPIO
3. Project Manager -> Advanced Settings -> Driver Selector -> LL
"""

    return final_code, hardware

# ========== STREAMLIT APP ==========
st.title("⚡ STM32 Professional Code Generator")
st.markdown("**Controller + Project Likho → LL Code + Hardware Wiring Mil Jaye Ga**")

col1, col2 = st.columns([1,2])
with col1:
    mcu_select = st.selectbox("1. STM32 Controller", ["STM32F103C8T6", "STM32F401RE"])
with col2:
    project_title = st.text_input("2. Project Ka Naam", "I2C MPU6050 + UART")

st.markdown("### 3. Hardware Pins Aur Kaam")
pins_text = st.text_area("Format: I2C SDA on PB7, UART TX on PA9",
"I2C SDA on PB7, I2C SCL on PB6, UART TX on PA9, UART RX on PA10", height=80)

project_desc = st.text_area("4. Project Detail Mein Likho - Kya Banana Hai?",
"I2C se MPU6050 ka data padho 100Hz. UART pe 115200 baud se PC ko bhejo.", height=120)

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
