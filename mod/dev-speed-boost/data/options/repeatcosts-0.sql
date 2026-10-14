-- Repeat costs at 0% for every player: how much each copy of a unit, building or
-- project adds to the cost of the next one.
UPDATE Units          SET CostProgressionParam1 = CostProgressionParam1 * 0 / 100;
UPDATE Constructibles SET CostProgressionParam1 = CostProgressionParam1 * 0 / 100;
UPDATE Projects       SET CostProgressionParam1 = CostProgressionParam1 * 0 / 100;
UPDATE GlobalParameters SET Value = CAST(Value AS INTEGER) * 0 / 100
    WHERE Name = 'BUILDING_COST_INCREASE_PERCENT_PER_CITY';
