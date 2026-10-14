-- Age length at 200% for every player: the age progress needed to end each age.
UPDATE AgeProgressions SET
    MaxPoints_Abbreviated = MAX(1, MaxPoints_Abbreviated * 200 / 100),
    MaxPoints_Standard    = MAX(1, MaxPoints_Standard * 200 / 100),
    MaxPoints_Long        = MAX(1, MaxPoints_Long * 200 / 100);
