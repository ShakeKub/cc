import sys
import time

import pyautogui

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.6


def click(x: int, y: int) -> None:
    pyautogui.click(x, y)
    time.sleep(0.7)


def scroll_down(times: int) -> None:
    for _ in range(times):
        pyautogui.scroll(-500)
        time.sleep(0.3)


def type_text(text: str) -> None:
    pyautogui.typewrite(text, interval=0.05)
    time.sleep(0.5)


def main() -> None:
    user_id = input("Zadejte ID: ").strip()
    if not user_id:
        print("ID nesmi byt prazdne.")
        sys.exit(1)

    print("Spusteni za 5 sekund - prepnete do ciloveho okna...")
    time.sleep(5)

    try:
        click(586, 693)
        type_text(user_id)

        click(837, 684)
        print("Cekam 10 sekund...")
        time.sleep(10)

        click(903, 422)
        click(893, 758)
        scroll_down(9)

        click(736, 180)
        click(764, 523)
        click(759, 711)
        scroll_down(9)

        click(723, 136)
        click(696, 519)
        click(716, 694)
        scroll_down(14)

        click(746, 855)
        type_text("JCHA")

        click(728, 675)
        print("Automatizace dokoncena.")

    except pyautogui.FailSafeException:
        print("\nBezpecnostni preruseni: mys detekovana v rohu obrazovky.")
        sys.exit(0)
    except KeyboardInterrupt:
        print("\nSkript prerusen uzivatelem.")
        sys.exit(0)
    except Exception as e:
        print(f"Chyba: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
