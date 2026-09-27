"""civ7lab: a test bench for Civilization VII mods.

Five routes to the same game, cheapest first:

  offline   apply a mod's SQL and XML to a copy of the game's own database,
            and parse its UI scripts, without launching anything
  live      attach to a running game over its UI debugger and ask a collector
            a question, with no reload
  ui        patch a mod's UI scripts into the running game on every save
  logs      read the structured records a probe printed, which survive the
            game exiting
  run       launch the game unattended, play or load, and harvest the lot

Nothing here is specific to one mod. Point it at a mod directory and it reads
that mod's modinfo for what to apply and what to check.
"""

__version__ = "0.1.0"
