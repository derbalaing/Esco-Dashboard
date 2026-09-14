from models.grid import GridModel

grid = GridModel(

    availability=90,

    outages=5,

    dt=5,

    seed=42

)

grid.reset()

for step in range(288):

    grid.step(step)

print(grid.dataframe())

print(grid.summary())