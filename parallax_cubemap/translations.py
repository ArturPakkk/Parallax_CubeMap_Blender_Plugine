# SPDX-License-Identifier: GPL-3.0-or-later
"""English source strings and Russian translations in a private Blender context."""
import bpy

CONTEXT = "Parallax_CubeMap"
RUSSIAN = {
    "Assign Debug_Parallax to the selected objects first": "Сначала назначьте Debug_Parallax выбранным объектам",
    "Parallax_CubeMap requires Blender 4.5 or newer": "Для Parallax_CubeMap нужен Blender 4.5 или новее",
    "Disable PX CubeMap Windows before enabling Parallax_CubeMap": "Отключите PX CubeMap Windows перед включением Parallax_CubeMap",
    "Assign Material": "Назначить материал",
    "Debug Texture": "Debug-текстура",
    "Restore Materials": "Вернуть материалы",
    "Save original materials and assign Debug_Parallax using UV 0–1; finish in Object Mode for Ctrl+Z":
        "Сохранить прежние материалы и назначить Debug_Parallax по UV 0–1; выход в Object Mode для Ctrl+Z",
    "Room / Debug for all windows; finish in Object Mode for correct Ctrl+Z":
        "Комната / Debug для всех окон; выход в Object Mode для корректного Ctrl+Z",
    "Restore saved materials on selected objects/faces while keeping later modelling edits":
        "Вернуть сохранённые материалы выбранных объектов/граней, сохранив последующее моделирование",
    "Missing bundled file: %s. Reinstall the addon ZIP":
        "В сборке отсутствует %s. Переустановите ZIP аддона",
    "Debug_Parallax is read-only (Linked Library)":
        "Debug_Parallax доступен только для чтения (Linked Library)",
    "Debug_Parallax belongs to another or modified material. Rename it; the addon preserves user materials":
        "Имя Debug_Parallax занято другим или изменённым материалом. Переименуйте его: аддон не перезаписывает чужие материалы",
    "Invalid EXR: %s. Expected RGBA 2048×2048":
        "Некорректная EXR: %s. Ожидается RGBA 2048×2048",
    "Debug_Parallax assigned to %d faces": "Debug_Parallax назначен на %d граней",
    "%d faces have no previous assignment history (before version 1.3)":
        "Для %d граней нет истории прежних назначений (до версии 1.3)",
    "Switch to Object Mode or Edit Mode": "Перейдите в Object Mode или Edit Mode",
    "Assign Debug_Parallax first": "Сначала назначьте материал Debug_Parallax",
    "Original materials were deleted. Restoring by name alone is unsafe":
        "Исходные материалы удалены. Возврат по одному лишь имени небезопасен",
    "Materials on the saved faces were changed manually; those faces were skipped":
        "На сохранённых гранях материал уже изменён вручную; они пропущены",
    "No saved materials. Backups are created by assignments made in version 1.3 or later":
        "Нет сохранённых материалов. История создаётся при назначении начиная с версии 1.3",
    "Original materials restored on %d faces": "Прежние материалы возвращены на %d граней",
    "Skipped: manually changed — %d, deleted original materials — %d":
        "Пропущено: изменены вручную — %d, удалены исходные материалы — %d",
    "Another copy of Parallax_CubeMap is already enabled. Disable the duplicate (legacy/extension), then enable this copy":
        "Уже включена другая копия Parallax_CubeMap. Отключите дубликат (legacy/extension), затем включите эту копию",
    "Material name is already in use: ": "Имя материала уже занято: ",
    "Material slot limit reached: ": "Достигнут лимит material slots: ",
    "Select window mesh objects or faces in Edit Mode": "Выберите Mesh-объекты окон или грани в Edit Mode",
    "Object or Mesh is read-only: ": "Объект или Mesh доступен только для чтения: ",
    "No UV map: %s. Create UVs within 0–1": "Нет UV-развёртки: %s. Создайте UV в пределах 0–1",
    "UV coordinates are outside 0–1: ": "UV выходит за пределы 0–1: ",
    "Degenerate face or UV map: ": "Вырожденная грань или UV-развёртка: ",
    "No window faces selected": "Нет выбранных граней окон",
    "Material restore data conflict: ": "Конфликт данных возврата материалов: ",
    "Material restore data is damaged: ": "Данные возврата материалов повреждены: ",
    "Restore data conflict: ": "Конфликт данных возврата: ",
    "Mesh instance is read-only: ": "Экземпляр Mesh доступен только для чтения: ",
    "Not enough material slots for restoration: ": "Недостаточно material slots для возврата: ",
}
TRANSLATIONS = {"ru_RU": {(CONTEXT, english): russian for english, russian in RUSSIAN.items()}}


def tr(message):
    # Follow Blender's actual interface language and its translation setting.
    # Material and datablock names are never passed through this function.
    return bpy.app.translations.pgettext_iface(message, CONTEXT)


def register(module_name):
    bpy.app.translations.unregister(module_name)
    bpy.app.translations.register(module_name, TRANSLATIONS)


def unregister(module_name):
    bpy.app.translations.unregister(module_name)
