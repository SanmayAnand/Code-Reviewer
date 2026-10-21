import os
import tempfile

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

BASE_URL = os.environ.get("APP_URL", "http://127.0.0.1:8000")

SET_VALUE = """
const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
setter.call(arguments[0], arguments[1]);
arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
"""

TWO_SMELLS = (
    "def a(p1, p2, p3, p4, p5, p6):\n"
    "    return p1\n\n\n"
    "def b(x):\n"
    "    if x:\n"
    "        for i in x:\n"
    "            while i:\n"
    "                if i:\n"
    "                    if i:\n"
    "                        return i\n"
)


@pytest.fixture
def driver():
    options = webdriver.ChromeOptions()
    if not os.environ.get("HEADED"):
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1400,1000")
    d = webdriver.Chrome(options=options)
    d.get(BASE_URL)
    WebDriverWait(d, 15).until(EC.presence_of_element_located((By.ID, "code-input")))
    yield d
    d.quit()


def wait(d, seconds=60):
    return WebDriverWait(d, seconds)


def set_code(d, text):
    d.execute_script(SET_VALUE, d.find_element(By.ID, "code-input"), text)


def choose_language(d, value):
    Select(d.find_element(By.XPATH, "//label[contains(., 'Language')]//select")).select_by_value(value)


def choose_sample(d, index):
    Select(d.find_element(By.CSS_SELECTOR, "select[aria-label='Sample snippets']")).select_by_value(str(index))


def review(d):
    d.find_element(By.CSS_SELECTOR, "button.primary").click()
    wait(d).until(lambda x: x.find_elements(By.CSS_SELECTOR, ".summary, .banner"))


def cards(d):
    return d.find_elements(By.CSS_SELECTOR, "article.card")


def test_ui_01_page_loads(driver):
    assert "Code Reviewer" in driver.title
    assert "code reviewer" in driver.find_element(By.TAG_NAME, "h1").text.lower()
    wait(driver).until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".pill")))
    assert not driver.find_element(By.CSS_SELECTOR, "button.primary").is_enabled()


def test_ui_02_python_sample_review(driver):
    choose_sample(driver, 0)
    review(driver)
    found = cards(driver)
    assert len(found) == 2
    assert found[0].find_element(By.CSS_SELECTOR, ".badge").text.lower() == "high"
    assert "deep nesting" in found[0].find_element(By.TAG_NAME, "strong").text.lower()
    assert "long parameter list" in found[1].find_element(By.TAG_NAME, "strong").text.lower()


def test_ui_03_java_sample_review(driver):
    choose_sample(driver, 2)
    review(driver)
    assert len(cards(driver)) == 2
    assert Select(driver.find_element(By.XPATH, "//label[contains(., 'Language')]//select")).first_selected_option.get_attribute("value") == "java"


def test_ui_04_parse_error_banner(driver):
    choose_language(driver, "python")
    set_code(driver, "def f(:")
    review(driver)
    banner = driver.find_element(By.CSS_SELECTOR, ".banner.error")
    assert "Python syntax error on line 1" in banner.text


def test_ui_05_no_issues_message(driver):
    set_code(driver, "def add(a, b): return a + b")
    review(driver)
    assert "No design-level issues detected" in driver.find_element(By.CSS_SELECTOR, ".empty").text
    assert len(cards(driver)) == 0


def test_ui_06_sort_by_line_number(driver):
    set_code(driver, TWO_SMELLS)
    review(driver)
    assert cards(driver)[0].find_element(By.CSS_SELECTOR, "code.target").text == "b"
    Select(driver.find_element(By.CSS_SELECTOR, ".summary select")).select_by_value("line")
    assert cards(driver)[0].find_element(By.CSS_SELECTOR, "code.target").text == "a"


def test_ui_07_history_reopen_and_delete(driver):
    choose_sample(driver, 0)
    review(driver)
    wait(driver).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, ".hitem")) == 1)
    driver.find_element(By.CSS_SELECTOR, ".hopen").click()
    assert len(cards(driver)) == 2
    driver.find_element(By.CSS_SELECTOR, "button[aria-label='Delete review']").click()
    wait(driver).until(lambda d: "No reviews yet." in d.find_element(By.CSS_SELECTOR, "aside.history").text)


def test_ui_08_file_upload(driver):
    source = "def add(a, b):\n    return a + b\n"
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "sample_upload.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(source)
        field = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
        driver.execute_script("arguments[0].hidden = false; arguments[0].style.display = 'block';", field)
        field.send_keys(path)
        wait(driver).until(lambda d: d.find_element(By.ID, "code-input").get_attribute("value") == source)
    selected = Select(driver.find_element(By.XPATH, "//label[contains(., 'Language')]//select")).first_selected_option
    assert selected.get_attribute("value") == "python"


def test_ui_09_help_panel_toggle(driver):
    toggle = driver.find_element(By.XPATH, "//button[normalize-space()='How it works']")
    toggle.click()
    assert driver.find_element(By.CSS_SELECTOR, "section.help").is_displayed()
    driver.find_element(By.XPATH, "//button[normalize-space()='Close help']").click()
    assert len(driver.find_elements(By.CSS_SELECTOR, "section.help")) == 0


def test_ui_10_report_actions_available(driver):
    choose_sample(driver, 0)
    review(driver)
    assert driver.find_element(By.XPATH, "//button[normalize-space()='Copy']").is_displayed()
    assert driver.find_element(By.XPATH, "//button[normalize-space()='Download .md']").is_displayed()
    assert "AI-assisted" in driver.find_element(By.CSS_SELECTOR, ".disclaimer").text