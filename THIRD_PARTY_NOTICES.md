# Сторонние компоненты

Установочный ZIP не содержит сторонних Python-пакетов, исполняемых файлов,
моделей, HDRI или текстур неизвестного происхождения.

- **Blender** — отдельная среда исполнения и инструмент генерации комнаты;
  [лицензия Blender](https://www.blender.org/about/license/).
- **Python** — инструменты сборки и тестирования; PSF License,
  [условия Python](https://docs.python.org/3/license.html).
- **NumPy** — генерация атласа и проверки изображений; BSD-3-Clause,
  [лицензия NumPy](https://numpy.org/doc/stable/license.html).
- **GitHub Actions checkout/setup-python/upload-artifact** — только CI;
  закреплены на commit SHA в workflow и не включаются в ZIP.

Эти среды и библиотеки не копируются в установочный пакет.
Обе поставляемые EXR и авторство описаны в [ASSET_NOTICE.txt](ASSET_NOTICE.txt).
