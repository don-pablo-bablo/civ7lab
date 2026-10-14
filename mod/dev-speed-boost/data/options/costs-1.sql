-- Costs at 1% for every player. Integer arithmetic; MAX keeps every cost at least 1.
UPDATE Constructibles        SET Cost = MAX(1, Cost * 1 / 100);
UPDATE Unit_Costs            SET Cost = MAX(1, Cost * 1 / 100);
UPDATE ProgressionTreeNodes  SET Cost = MAX(1, Cost * 1 / 100);
UPDATE Projects              SET Cost = MAX(1, Cost * 1 / 100);
