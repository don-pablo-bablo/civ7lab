-- Age length at 10% for every player: the age progress needed to end each age.
UPDATE AgeProgressions SET
    MaxPoints_Abbreviated = MAX(1, MaxPoints_Abbreviated * 10 / 100),
    MaxPoints_Standard    = MAX(1, MaxPoints_Standard * 10 / 100),
    MaxPoints_Long        = MAX(1, MaxPoints_Long * 10 / 100);
