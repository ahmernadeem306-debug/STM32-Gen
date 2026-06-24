import streamlit as st
import re

st.set_page_config(page_title="⚡ STM32 Professional Code Generator", layout="wide", page_icon="⚡")


# ========== Saare STM32 Controllers + Unke Default Pins ==========
MCU = {
    "STM32F103C8T6": {"freq": 72, "family": "F1", "pins": {
        "I2C1_SDA": "PB7", "I2C1_SCL": "PB6", "USART1_TX": "PA9", "USART1_RX": "PA10",
        "TIM2_CH1": "PA0", "TIM3_CH1": "PA6", "TIM4_CH1": "PB6", "ADC1_IN0": "PA0", "SPI1_MOSI": "PA7", "SPI1_MISO": "PA6", "SPI1_SCK": "PA5"
    }},
    "STM32F401RE": {"freq": 84, "family": "F4", "pins": {
        "I2C1_SDA": "PB7", "I2C1_SCL": "PB6", "USART2_TX": "PA2", "USART2_RX": "PA3",
        "TIM2_CH1": "PA0", "ADC1_IN0": "PA0"
    }},
}

def explain(line, reason):
    return f"{line} // Asaan Zuban: {reason}"

def auto_build(mcu_name, user_text):
    mcu = MCU[mcu_name]
    text = user_text.lower()
    f = mcu["family"].lower()
    freq = mcu["freq"]
    pins = mcu["pins"]

    includes = {f"stm32{f}xx_ll_bus.h", f"stm32{f}xx_ll_rcc.h", f"stm32{f}xx_ll_gpio.h", f"stm32{f}xx_ll_utils.h"}
    init_code = []
    loop_code = []
    gpio_init = []
    wiring = []

    # ========== SMART DETECTION - ELIF KHATAM ==========

    # 1. Clock - Hamesha chahiye
    clock = f""" LL_RCC_HSE_Enable(); // Ye line crystal ON karti hai kyun ke crystal accurate hota hai
  while(LL_RCC_HSE_IsReady()!= 1) {{}}; // Jab tak crystal chalu na ho, yahin ruko
  LL_RCC_PLL_ConfigDomain_SYS(LL_RCC_PLLSOURCE_HSE_DIV_1, LL_RCC_PLL_MUL_9); // 8MHz ko 9 se multiply karke 72MHz banate hain
  LL_RCC_PLL_Enable(); // PLL ON karo
  while(LL_RCC_PLL_IsReady()!= 1) {{}};
  LL_RCC_SetAPB1Prescaler(LL_RCC_APB1_DIV_2); // APB1 bus 36MHz se zyada nahi chal sakti
  LL_RCC_SetSysClkSource(LL_RCC_SYS_CLKSOURCE_PLL); // Poore system ko 72MHz pe chala do"""

    # 2. I2C Detect Karo
    if any(word in text for word in ["i2c", "mpu6050", "oled", "ssd1306", "gyro", "accel"]):
        includes.add(f"stm32{f}xx_ll_i2c.h")
        sda, scl = pins["I2C1_SDA"], pins["I2C1_SCL"]
        gpio_init.append(explain(f"LL_AHB1_GRP1_EnableClock(LL_AHB1_GRP1_PERIPH_GPIO{sda[1]});", f"Port {sda[1]} ka bijli ka switch ON karo"))
        gpio_init.append(explain(f"LL_GPIO_SetPinMode(GPIO{sda[1]}, LL_GPIO_PIN_{sda[2:]}, LL_GPIO_MODE_ALTERNATE);", f"Pin {sda} ko I2C SDA banane ke liye Alternate mode pe lagao"))
        gpio_init.append(explain(f"LL_GPIO_SetPinOutputType(GPIO{sda[1]}, LL_GPIO_PIN_{sda[2:]}, LL_GPIO_OUTPUT_OPENDRAIN);", f"I2C ke liye pin open-drain hona zaroori hai"))
        gpio_init.append(explain(f"LL_GPIO_SetPinPull(GPIO{sda[1]}, LL_GPIO_PIN_{sda[2:]}, LL_GPIO_PULL_UP);", f"I2C line ko 3.3V pe kheench ke rakhne ke liye pull-up lagao"))

        init_code.append(explain("LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_I2C1);", "I2C1 ka bijli ka switch ON karo"))
        init_code.append(explain("LL_I2C_SetTiming(I2C1, 0x00201D2B);", "Ye number 72MHz ko 100kHz I2C speed mein convert karta hai"))
        init_code.append(explain("LL_I2C_Enable(I2C1);", "I2C ko chalu karo"))
        wiring.append(f"I2C SDA: STM32 {sda} -> Sensor SDA | 4.7k resistor SDA se 3.3V pe lagao warna kaam nahi kare ga")
        wiring.append(f"I2C SCL: STM32 {scl} -> Sensor SCL | 4.7k resistor SCL se 3.3V pe lagao")

        if "mpu6050" in text:
            loop_code.append(explain("// MPU6050 ko jagao", "Register 0x6B mein 0x00 likhne se MPU6050 ON ho jata hai"))
            loop_code.append("LL_I2C_HandleTransfer(I2C1, 0x68<<1, LL_I2C_ADDRSLAVE_7BIT, 2, LL_I2C_MODE_AUTOEND, LL_I2C_GENERATE_START_WRITE);")
            loop_code.append(explain("LL_I2C_TransmitData8(I2C1, 0x6B); LL_I2C_TransmitData8(I2C1, 0x00);", "Pehle register ka address 0x6B bhejo, phir value 0x00"))

    # 3. UART Detect Karo
    if any(word in text for word in ["uart", "serial", "pc", "baud", "115200", "g-code", "json"]):
        includes.add(f"stm32{f}xx_ll_usart.h")
        tx = pins.get("USART1_TX", pins.get("USART2_TX"))
        rx = pins.get("USART1_RX", pins.get("USART2_RX"))
        gpio_init.append(explain(f"LL_GPIO_SetPinMode(GPIO{tx[1]}, LL_GPIO_PIN_{tx[2:]}, LL_GPIO_MODE_ALTERNATE);", f"Pin {tx} ko UART TX banane ke liye Alternate mode"))
        init_code.append(explain("LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_USART1);", "UART1 ka bijli ka switch ON karo"))
        init_code.append(explain(f"LL_USART_SetBaudRate(USART1, {freq}000000, LL_USART_OVERSAMPLING_16, 115200);", "PC se baat karne ki speed 115200 set karo"))
        init_code.append(explain("LL_USART_EnableDirectionTx(USART1); LL_USART_Enable(USART1);", "UART ko bhejne ke liye ON karo"))
        wiring.append(f"UART TX: STM32 {tx} -> FTDI/USB-TTL ka RX pin")
        wiring.append(f"UART RX: STM32 {rx} -> FTDI/USB-TTL ka TX pin")
        loop_code.append(explain('LL_USART_TransmitData8(USART1, "A");', "UART se PC ko 'A' letter bhejo"))

    # 4. PWM/Motor Detect Karo
    if any(word in text for word in ["pwm", "motor", "esc", "servo", "50hz", "20khz"]):
        includes.add(f"stm32{f}xx_ll_tim.h")
        pwm_pin = pins["TIM2_CH1"]
        gpio_init.append(explain(f"LL_GPIO_SetPinMode(GPIO{pwm_pin[1]}, LL_GPIO_PIN_{pwm_pin[2:]}, LL_GPIO_MODE_ALTERNATE);", f"Pin {pwm_pin} ko PWM banane ke liye Timer se jodo"))
        init_code.append(explain("LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_TIM2);", "Timer2 ka bijli ka switch ON karo"))
        init_code.append(explain("LL_TIM_SetPrescaler(TIM2, 7199);", "72MHz ko 7200 se divide karke 10kHz banaya"))
        init_code.append(explain("LL_TIM_SetAutoReload(TIM2, 199);", "10kHz ko 200 se divide karke 50Hz PWM banaya - ESC ke liye"))
        init_code.append(explain("LL_TIM_CC_EnableChannel(TIM2, LL_TIM_CHANNEL_CH1); LL_TIM_EnableCounter(TIM2);", "PWM chalu karo"))
        wiring.append(f"PWM: STM32 {pwm_pin} -> ESC ka Signal wire | ESC ki GND STM32 GND se milao")

    # 5. ADC Detect Karo
    if any(word in text for word in ["adc", "sensor", "temperature", "voltage", "current", "kwh"]):
        includes.add(f"stm32{f}xx_ll_adc.h")
        adc_pin = pins["ADC1_IN0"]
        gpio_init.append(explain(f"LL_GPIO_SetPinMode(GPIO{adc_pin[1]}, LL_GPIO_PIN_{adc_pin[2:]}, LL_GPIO_MODE_ANALOG);", f"Pin {adc_pin} ko Analog bana do sensor padhne ke liye"))
        init_code.append(explain("LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_ADC1);", "ADC ka bijli ka switch ON karo"))
        init_code.append(explain("LL_ADC_REG_SetSequencerRanks(ADC1, LL_ADC_REG_RANK_1, LL_ADC_CHANNEL_0);", "Channel 0 se padhna shuru karo"))
        init_code.append(explain("LL_ADC_Enable(ADC1);", "ADC chalu karo"))
        wiring.append(f"ADC: Sensor ka Output -> STM32 {adc_pin} | Sensor ki GND STM32 GND se milao")
        loop_code.append(explain("LL_ADC_REG_StartConversionSWStart(ADC1);", "Sensor padhna shuru karo"))
        loop_code.append(explain("while(!LL_ADC_IsActiveFlag_EOC(ADC1)){}; uint16_t val = LL_ADC_REG_ReadConversionData12(ADC1);", "Jab tak padh na jaye ruko, phir value uthao"))

    # 6. SPI Detect Karo
    if any(word in text for word in ["spi", "sd card", "display", "tft"]):
        includes.add(f"stm32{f}xx_ll_spi.h")
        mosi = pins["SPI1_MOSI"]
        wiring.append(f"SPI MOSI: STM32 {mosi} -> SD Card MOSI")
        wiring.append(f"SPI SCK: STM32 {pins['SPI1_SCK']} -> SD Card SCK")
        init_code.append(explain("LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_SPI1);", "SPI ka bijli ka switch ON karo"))

    # ========== FINAL CODE ASSEMBLY ==========
    wiring.append("GND Common: STM32 ka GND, Sensor ka GND, Motor ka GND sab ek saath jodo warna kaam nahi kare ga")
    wiring.append("Power: STM32 ke 3.3V pin se sensor ko bijli do. 5V wale sensor ko 5V do")

    final_code = f"""/*
 * Project: {user_text}
 * MCU: {mcu_name} @ {freq}MHz
 * Asaan Comments: Har line ke neeche likha hai ye kya karti hai
 */

{chr(10).join([f'#include "{inc}"' for inc in sorted(includes)])}

void SystemClock_Config(void);
void GPIO_Config(void);

int main(void) {{
  // Pehle bijli aur speed set karo
  SystemClock_Config();
  GPIO_Config();
  LL_Init1msTick({freq}000000); // 1ms ka timer chalu karo. 1ms = 1 second ka 1000vaan hissa

{chr(10).join([' '+line for line in init_code])}

  while(1) {{
{chr(10).join([' '+line for line in loop_code])}
    LL_mDelay(100); // 100ms ruko. Ye line CPU ko araam deti hai
  }}
}}

void GPIO_Config(void) {{
{chr(10).join([' '+line for line in gpio_init])}
}}

void SystemClock_Config(void) {{
{chr(10).join([' '+line for line in clock.split(chr(10))])}
}}
"""
    hw = f"""HARDWARE WIRING - Bilkul Asaan Zuban Mein:
{chr(10).join([f"{i+1}. {w}" for i, w in enumerate(wiring)])}

Zaroori Baat:
1. 4.7k resistor I2C ke liye lagana bhool gaye to kaam nahi kare ga
2. GND sab ka common karo warna sensor pagal ho jaye ga
3. CubeIDE mein Project -> Build -> Run
"""
    return final_code, hw

# ========== STREAMLIT APP ==========
st.title("⚡ STM32 Universal Generator ")
st.markdown("**Code + Wiring khud ban jaye ga**")

mcu_select = st.selectbox("1. STM32 Controller", list(MCU.keys()))
st.info(f"Is MCU ke Auto Pins: I2C={MCU[mcu_select]['pins']['I2C1_SDA']}, UART={MCU[mcu_select]['pins'].get('USART1_TX','USART2_TX')}")

project_desc = st.text_area("2. Project Kya Banana Hai? Kuch Bhi Likho",
"Drone banao. I2C se gyro padho. 4 motors ko PWM se chalao. UART se PC ko data bhejo.", height=150)

if st.button("🚀 BANA DO CODE + WIRING", type="primary", use_container_width=True):
    with st.spinner("Dimag laga raha hun..."):
        code, hw = auto_build(mcu_select, project_desc)
        st.success("✅ Tayyar! Neeche dekh lo")

        tab1, tab2 = st.tabs(["📄 main.c Code", "🔌 Hardware Wiring"])
        with tab1:
            st.code(code, language="c", line_numbers=True)
        with tab2:
            st.code(hw, language="text")

