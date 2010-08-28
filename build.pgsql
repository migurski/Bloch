SELECT DropGeometryColumn('', 'bloch_shared_borders', 'the_geom');
DROP TABLE bloch_shared_borders;

CREATE TABLE bloch_shared_borders
(
    gid1    INTEGER,
    gid2    INTEGER
);

SELECT AddGeometryColumn('', 'bloch_shared_borders', 'the_geom', 900913, 'MULTILINESTRING', 2);

SELECT DropGeometryColumn('', 'bloch_unshared_borders', 'the_geom');
DROP TABLE bloch_unshared_borders;

CREATE TABLE bloch_unshared_borders
(
    gid INTEGER
);

SELECT AddGeometryColumn('', 'bloch_unshared_borders', 'the_geom', 900913, 'MULTILINESTRING', 2);

SELECT DropGeometryColumn('', 'bloch_rebuilt_polygons', 'the_geom');
DROP TABLE bloch_rebuilt_polygons;

CREATE TABLE bloch_rebuilt_polygons
(
    gid INTEGER
);

SELECT AddGeometryColumn('', 'bloch_rebuilt_polygons', 'the_geom', 900913, 'MULTIPOLYGON', 2);



DELETE FROM bloch_shared_borders;

INSERT INTO bloch_shared_borders
    SELECT c1.gid AS gid1,
           c2.gid AS gid1,
           ST_Multi(ST_Intersection(c1.the_geom, c2.the_geom))

    -- join this table on itself
    FROM bloch_counties AS c1
    LEFT OUTER JOIN bloch_counties AS c2
      ON ST_Intersects(c1.the_geom, c2.the_geom)
     AND c1.gid != c2.gid
    
    -- include only the intersections that appear to be linear
    WHERE ST_GeometryType(ST_Multi(ST_Intersection(c1.the_geom, c2.the_geom))) = 'ST_MultiLineString'
    ORDER BY c1.gid, c2.gid;



DELETE FROM bloch_unshared_borders;

INSERT INTO bloch_unshared_borders
    SELECT gid,
       ST_Multi(
           -- needs to include islands (diff is null) and landlocked (diff is empty)
           CASE WHEN diff_geom IS NULL THEN full_geom
                WHEN ST_IsEmpty(diff_geom) THEN NULL
                ELSE diff_geom
           END
       )
    FROM (
        -- use a subselect to simplify the above
        SELECT original.gid AS gid,

               -- TODO: make this work for original multipolygons, maybe ST_Dump earlier?
               ST_ExteriorRing(ST_GeometryN(original.the_geom, 1)) AS full_geom,
               
               -- the part of the border that's not in shared
               ST_Difference(ST_ExteriorRing(ST_GeometryN(original.the_geom, 1)),
                             ST_Multi(ST_Union(shared.the_geom))) AS diff_geom

        FROM bloch_counties AS original
        LEFT OUTER JOIN bloch_shared_borders AS shared
          ON shared.gid1 = original.gid
        GROUP BY original.gid, original.the_geom
    ) AS x;



DELETE FROM bloch_rebuilt_polygons;

INSERT INTO bloch_rebuilt_polygons
    SELECT original.gid,
           ST_Multi(ST_BuildArea(ST_Collect(shared.the_geom, unshared.the_geom)))

    FROM bloch_counties AS original

    -- a geometry collection of the shared borders
    LEFT OUTER JOIN (
        SELECT gid, ST_Collect(the_geom) AS the_geom
        FROM bloch_unshared_borders
        GROUP BY gid
    ) AS shared ON shared.gid = original.gid

    -- a geometry collection of the unshared borders
    LEFT OUTER JOIN (
        SELECT gid1 AS gid, ST_Collect(the_geom) AS the_geom
        FROM bloch_shared_borders
        GROUP BY gid1
    ) AS unshared ON unshared.gid = original.gid;
