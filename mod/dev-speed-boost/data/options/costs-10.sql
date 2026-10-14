-- Costs at 10% for every player. Integer arithmetic; MAX keeps every cost at least 1.
UPDATE Constructibles        SET Cost = MAX(1, Cost * 10 / 100);
UPDATE Unit_Costs            SET Cost = MAX(1, Cost * 10 / 100);
UPDATE ProgressionTreeNodes  SET Cost = MAX(1, Cost * 10 / 100);
UPDATE Projects              SET Cost = MAX(1, Cost * 10 / 100);
