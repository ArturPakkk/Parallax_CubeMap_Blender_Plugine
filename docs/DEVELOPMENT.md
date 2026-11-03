# Development

Requires Python 3.11+ for tools, and Blender 4.5+ for integration tests.
The installable addon is in parallax_cubemap; the repository root is not an addon ZIP.

Build:
    python tools/package.py

Package and source checks:
    python -m unittest discover -s tests -p test_package.py -v

Run the data tests in a factory Blender process:
    blender --background --factory-startup --offline-mode --python-exit-code 1 --python tests/regressions.py
    blender --background --factory-startup --offline-mode --python-exit-code 1 --python tests/restore.py
    blender --background --factory-startup --offline-mode --python-exit-code 1 --python tests/conflicts.py

CI uses native Blender executables rather than embedded bpy wheels, matching the installed addon environment.
tests/verify.py adds EEVEE/Cycles renders and needs a graphics-capable Blender.
tests/restore_reload.py opens the fixture written by restore.py in a new process.
tests/install.py tests the built ZIP with a separate BLENDER_USER_RESOURCES profile.

tests/undo_ui.py and tests/language_ui.py require a separate UI process, not the
user's working Blender session. Set BLENDER_USER_RESOURCES, BLENDER_USER_CONFIG,
BLENDER_USER_EXTENSIONS and BLENDER_USER_SCRIPTS to isolated temporary paths;
create the profile's undo/temp or language/temp directories first.

Generated files stay in ignored GARBAGE/ and dist/. CI tests pinned official native Blender
builds and creates a GitHub Release ZIP after all checks pass on main or a version tag.
An existing version's published assets are never overwritten; bump the version for code changes.

The original room can be regenerated with:
    blender --background --factory-startup --python tools/create_room.py
Rendering may vary slightly between Blender builds; packaging always uses the committed atlas.
