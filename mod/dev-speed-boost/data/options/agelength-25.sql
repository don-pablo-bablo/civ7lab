-- Age length at 25% for every player: the age progress needed to end each age.
UPDATE AgeProgressions SET
    MaxPoints_Abbreviated = MAX(1, MaxPoints_Abbreviated * 25 / 100),
    MaxPoints_Standard    = MAX(1, MaxPoints_Standard * 25 / 100),
    MaxPoints_Long        = MAX(1, MaxPoints_Long * 25 / 100);
