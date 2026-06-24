import streamlit as st
import re

st.set_page_config(page_title="STM32 Easy CodeGen", layout="wide", page_icon="⚡")

# ========== SAARY STM32 Controllers ==========
MCU_DATABASE = {
    "STM32F103C8T6": {"freq": "72MHz", "family": "F1", "pins": {"I2C1_SDA": "PB7", "I2C1_SCL": "PB6", "USART1_TX": "PA9", "USART1_RX": "PA10", "TIM2_CH1": "PA0"}},
    "STM32F401RE": {"freq": "84MHz", "family": "F4", "pins": {"I2C1_SDA": "PB7", "I2C1_SCL": "PB6", "USART2_TX": "PA2", "USART2_RX": "PA3", "TIM2_CH1": "PA0"}},
    "STM32F407VG": {"freq": "168MHz", "family": "F4", "pins": {"I2C1_SDA": "PB7", "I2C1_SCL": "PB6", "USART1_TX": "PA9", "USART1_RX": "PA10"}},
    "STM32F030C8T6": {"freq": "48MHz", "family": "F0", "pins": {"I2C1_SDA": "PB7", "I2C1_SCL": "PB6", "USART1_TX": "PA9", "USART1_RX": "PA10"}},
    "STM32G431RB": {"freq": "170MHz", "family": "G4", "pins": {"I2C1_SDA": "PB7", "I2C1_SCL": "PB6", "USART1_TX": "PC4", "USART1_RX": "PC5"}},
    "STM32H743ZI": {"freq": "480MHz", "family": "H7", "pins": {"I2C1_SDA": "PB7", "I2C1_SCL": "PB6", "USART1_TX": "PA9", "USART1_RX": "PA10"}},
}

def get_clock_code(mcu):
    f = mcu["family"]
    freq = mcu["freq"]
    if f == "F1":
        return f""" LL_RCC_HSE_Enable(); // Ye line external 8MHz crystal ON karti hai. Crystal zayada accurate hota HSI se
  while(LL_RCC_HSE_IsReady()!= 1) {{}}; // Jab tak crystal ready na ho, yahin ruko
  /* PLL se 72MHz banate hain. Formula: 8MHz * 9 = 72MHz. F103 ka max 72MHz hai */
  LL_RCC_PLL_ConfigDomain_SYS(LL_RCC_PLLSOURCE_HSE_DIV_1, LL_RCC_PLL_MUL_9);
  LL_RCC_PLL_Enable(); // PLL ON karo
  while(LL_RCC_PLL_IsReady()!= 1) {{}}; // PLL ready hone tak wait
  LL_RCC_SetAPB1Prescaler(LL_RCC_APB1_DIV_2); // APB1 ka max 36MHz hai. 72/2=36MHz
  LL_RCC_SetSysClkSource(LL_RCC_SYS_CLKSOURCE_PLL); // System clock ko PLL pe set karo"""
    elif f == "F4":
        return f""" LL_RCC_HSI_Enable(); // Nucleo boards pe crystal nahi hota, is liye internal HSI use karo
  while(LL_RCC_HSI_IsReady()!= 1) {{}};
  /* {freq} ke liye PLL config. Example 84MHz: 16MHz/8*84/2=84MHz */
  LL_RCC_PLL_ConfigDomain_SYS(LL_RCC_PLLSOURCE_HSI, LL_RCC_PLLM_DIV_8, 84, LL_RCC_PLLP_DIV_2);
  LL_RCC_PLL_Enable();
  while(LL_RCC_PLL_IsReady()!= 1) {{}};
  LL_FLASH_SetLatency(LL_FLASH_LATENCY_2); // 84MHz pe Flash ko 2 wait state chahiye warna crash
  LL_RCC_SetSysClkSource(LL_RCC_SYS_CLKSOURCE_PLL);"""
    else:
        return f" // {f} family ka clock config - Datasheet dekho"

def generate_project(mcu_name, project_desc):
    mcu = MCU_DATABASE[mcu_name]
    desc = project_desc.lower()
    pins = mcu["pins"]
    f = mcu["family"].lower()
    includes = [f"stm32{f}xx_ll_bus.h", f"stm32{f}xx_ll_rcc.h", f"stm32{f}xx_ll_gpio.h", f"stm32{f}xx_ll_utils.h"]

    code = ""
    wiring = []
    gpio_init = ""

    # ========== AUTO PROJECT DETECTION ==========
    if "mpu6050" in desc or "i2c" in desc or "gyro" in desc:
        includes += [f"stm32{f}xx_ll_i2c.h", f"stm32{f}xx_ll_usart.h"]
        sda, scl = pins["I2C1_SDA"], pins["I2C1_SCL"]
        tx, rx = pins.get("USART1_TX", pins.get("USART2_TX")), pins.get("USART1_RX", pins.get("USART2_RX"))

        gpio_init = f""" LL_AHB1_GRP1_EnableClock(LL_AHB1_GRP1_PERIPH_GPIO{tx[1]}); // TX/RX wale port ka clock ON karo
  LL_AHB1_GRP1_EnableClock(LL_AHB1_GRP1_PERIPH_GPIO{sda[1]}); // SDA/SCL wale port ka clock ON karo

  /* I2C SDA Pin: {sda} - I2C mein dono lines open-drain hoti hain + pull-up zaroori */
  LL_GPIO_SetPinMode(GPIO{sda[1]}, LL_GPIO_PIN_{sda[2:]}, LL_GPIO_MODE_ALTERNATE);
  LL_GPIO_SetPinOutputType(GPIO{sda[1]}, LL_GPIO_PIN_{sda[2:]}, LL_GPIO_OUTPUT_OPENDRAIN);
  LL_GPIO_SetPinPull(GPIO{sda[1]}, LL_GPIO_PIN_{sda[2:]}, LL_GPIO_PULL_UP);

  /* I2C SCL Pin: {scl} - Clock line bhi open-drain */
  LL_GPIO_SetPinMode(GPIO{scl[1]}, LL_GPIO_PIN_{scl[2:]}, LL_GPIO_MODE_ALTERNATE);
  LL_GPIO_SetPinOutputType(GPIO{scl[1]}, LL_GPIO_PIN_{scl[2:]}, LL_GPIO_OUTPUT_OPENDRAIN);
  LL_GPIO_SetPinPull(GPIO{scl[1]}, LL_GPIO_PIN_{scl[2:]}, LL_GPIO_PULL_UP);

  /* UART TX Pin: {tx} - Data bhejne ke liye push-pull */
  LL_GPIO_SetPinMode(GPIO{tx[1]}, LL_GPIO_PIN_{tx[2:]}, LL_GPIO_MODE_ALTERNATE);

  /* UART RX Pin: {rx} - Data lene ke liye input pull-up */
  LL_GPIO_SetPinMode(GPIO{rx[1]}, LL_GPIO_PIN_{rx[2:]}, LL_GPIO_MODE_ALTERNATE);
  LL_GPIO_SetPinPull(GPIO{rx[1]}, LL_GPIO_PIN_{rx[2:]}, LL_GPIO_PULL_UP);"""

        code = f""" // I2C1 Init 100kHz - Kyun 100kHz? MPU6050 400kHz support karta lekin 100kHz zyada stable hai
  LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_I2C1);
  LL_I2C_Disable(I2C1);
  LL_I2C_SetTiming(I2C1, 0x00201D2B); // Ye magic number 72MHz se 100kHz banata hai
  LL_I2C_Enable(I2C1);

  // UART Init 115200 - Kyun 115200? PC terminal ka standard baud rate hai
  LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_USART1);
  LL_USART_SetBaudRate(USART1, {mcu['freq'].replace('MHz','000000')}, LL_USART_OVERSAMPLING_16, 115200);
  LL_USART_EnableDirectionTx(USART1);
  LL_USART_Enable(USART1);

  // MPU6050 ko jagao - Register 0x6B mein 0x00 likho. 0x6B = PWR_MGMT_1 register
  LL_I2C_HandleTransfer(I2C1, 0x68<<1, LL_I2C_ADDRSLAVE_7BIT, 2, LL_I2C_MODE_AUTOEND, LL_I2C_GENERATE_START_WRITE);
  while(!LL_I2C_IsActiveFlag_TXIS(I2C1)) {{}}; // TX buffer khali hone ka wait karo
  LL_I2C_TransmitData8(I2C1, 0x6B); // Register address bhejo
  while(!LL_I2C_IsActiveFlag_TXIS(I2C1)) {{}};
  LL_I2C_TransmitData8(I2C1, 0x00); // Value 0 bhejo = wake up

  uint8_t data[6];
  while(1) {{
    // Gyro ka data padho - Register 0x43 se 6 bytes. 0x43 = GYRO_XOUT_H ka address
    LL_I2C_HandleTransfer(I2C1, 0x68<<1, LL_I2C_ADDRSLAVE_7BIT, 1, LL_I2C_MODE_SOFTEND, LL_I2C_GENERATE_START_WRITE);
    while(!LL_I2C_IsActiveFlag_TXIS(I2C1)) {{}};
    LL_I2C_TransmitData8(I2C1, 0x43); // Konsa register padhna hai

    LL_I2C_HandleTransfer(I2C1, 0x68<<1, LL_I2C_ADDRSLAVE_7BIT, 6, LL_I2C_MODE_AUTOEND, LL_I2C_GENERATE_RESTART_READ);
    for(int i=0; i<6; i++) {{
      while(!LL_I2C_IsActiveFlag_RXNE(I2C1)) {{}}; // Jab tak data na aaye wait karo
      data[i] = LL_I2C_ReceiveData8(I2C1); // 1 byte padho
    }}

    // UART se PC ko bhejo
    for(int i=0; i<6; i++) {{
      while(!LL_USART_IsActiveFlag_TXE(USART1)) {{}}; // TX buffer khali hai ya nahi check karo
      LL_USART_TransmitData8(USART1, data[i]); // 1 byte bhejo
    }}
    LL_mDelay(10); // 10ms ruko = 100Hz speed
  }}"""

        wiring = [
            f"1. I2C SDA: STM32 {sda} -> MPU6050 SDA | 4.7kΩ resistor SDA se 3.3V pe lagao",
            f"2. I2C SCL: STM32 {scl} -> MPU6050 SCL | 4.7kΩ resistor SCL se 3.3V pe lagao",
            f"3. UART TX: STM32 {tx} -> FTDI Module ka RX pin",
            f"4. UART RX: STM32 {rx} -> FTDI Module ka TX pin",
            "5. Power: STM32 3.3V pin -> MPU6050 VCC pin",
            "6. Ground: STM32 GND -> MPU6050 GND -> FTDI GND. Sab ka GND common hona zaroori",
            "7. Important: Agar 4.7k pull-up na lagao to I2C kaam nahi kare ga"
        ]

    elif "blink" in desc or "led" in desc:
        led_pin = "PC13" if "F1" in mcu_name else "PA5"
        gpio_init = f""" LL_AHB1_GRP1_EnableClock(LL_AHB1_GRP1_PERIPH_GPIO{led_pin[1]}); // LED wale port ka clock ON karo
  LL_GPIO_SetPinMode(GPIO{led_pin[1]}, LL_GPIO_PIN_{led_pin[2:]}, LL_GPIO_MODE_OUTPUT); // Pin ko output banao"""
        code = f""" while(1) {{
    LL_GPIO_TogglePin(GPIO{led_pin[1]}, LL_GPIO_PIN_{led_pin[2:]}); // LED ON/OFF toggle karo
    LL_mDelay(500); // 500ms ruko. 500ms ON + 500ms OFF = 1 second blink
  }}"""
        wiring = [f"1. LED: STM32 {led_pin} -> 220Ω Resistor -> LED ki lambi tang -> LED ki choti tang -> GND"]

    else:
        code = " while(1) {\n // Ye project abhi add nahi. Batao main bana doon\n }"
        wiring = ["Pins auto detect nahi hue. Project mein 'i2c', 'mpu6050', 'blink' likho"]

    # Final Assembly
    final_code = f"""/*
 * Project: {project_desc}
 * MCU: {mcu_name} @ {mcu['freq']}
 * Asaan Comments: Har line ke neeche Urdu mein likha hai ye kyun hai
 */

{chr(10).join([f'#include "{inc}"' for inc in list(dict.fromkeys(includes))])}

void SystemClock_Config(void);
void GPIO_Config(void);

int main(void) {{
  SystemClock_Config(); // Clock 72MHz pe set karo
  GPIO_Config(); // Pins setup karo
  LL_Init1msTick({mcu['freq'].replace('MHz','000000')}); // 1ms ka timer ON karo delay ke liye

{chr(10).join([' '+line for line in code.split(chr(10))])}
}}

void GPIO_Config(void) {{
{gpio_init}
}}

void SystemClock_Config(void) {{
{get_clock_code(mcu)}
}}
"""

    hw = f"""HARDWARE WIRING - Asaan Zuban Mein:
{chr(10).join(wiring)}

CLOCK TREE:
{mcu['freq']} - System kitni tez chal raha hai

CubeIDE Mein Bas Ye Karo:
1. New Project -> {mcu_name}
2. Code paste karo -> Build -> Run
"""
    return final_code, hw

# ========== STREAMLIT APP - PIN KHATAM ==========
st.title("⚡ STM32 Asaan Code Generator")
st.markdown("**Bas Project Likho. Pins App Khud Choose Kare Ga. Har Line Urdu Mein Samjhay Ga**")

col1, col2 = st.columns([1,2])
with col1:
    mcu_select = st.selectbox("1. STM32 Controller", list(MCU_DATABASE.keys()))
with col2:
    st.info(f"Auto Pins: I2C={MCU_DATABASE[mcu_select]['pins'].get('I2C1_SDA', 'N/A')}, UART={MCU_DATABASE[mcu_select]['pins'].get('USART1_TX', 'N/A')}")

project_desc = st.text_area("2. Project Kya Banana Hai? Bas Ye Likho",
"I2C se MPU6050 ka gyro data padho. UART se PC ko bhejo 115200 speed pe.", height=150)

if st.button("🚀 CODE + WIRING BANAO", type="primary", use_container_width=True):
    with st.spinner("Code ban raha hai..."):
        code, hw = generate_project(mcu_select, project_desc)
        st.success("✅ Tayyar! Copy karo")

        tab1, tab2 = st.tabs(["📄 main.c Code", "🔌 Hardware Wiring"])
        with tab1:
            st.code(code, language="c", line_numbers=True)
        with tab2:
            st.code(hw, language="text")

st.caption("Pin Likhne Ki Zaroorat Nahi | 100% LL Drivers | Har Line Explain")
