-- Age length at 150% for every player: the age progress needed to end each age.
UPDATE AgeProgressions SET
    MaxPoints_Abbreviated = MAX(1, MaxPoints_Abbreviated * 150 / 100),
    MaxPoints_Standard    = MAX(1, MaxPoints_Standard * 150 / 100),
    MaxPoints_Long        = MAX(1, MaxPoints_Long * 150 / 100);
