-- Age length at 50% for every player: the age progress needed to end each age.
UPDATE AgeProgressions SET
    MaxPoints_Abbreviated = MAX(1, MaxPoints_Abbreviated * 50 / 100),
    MaxPoints_Standard    = MAX(1, MaxPoints_Standard * 50 / 100),
    MaxPoints_Long        = MAX(1, MaxPoints_Long * 50 / 100);
