-- Age length at 300% for every player: the age progress needed to end each age.
UPDATE AgeProgressions SET
    MaxPoints_Abbreviated = MAX(1, MaxPoints_Abbreviated * 300 / 100),
    MaxPoints_Standard    = MAX(1, MaxPoints_Standard * 300 / 100),
    MaxPoints_Long        = MAX(1, MaxPoints_Long * 300 / 100);
