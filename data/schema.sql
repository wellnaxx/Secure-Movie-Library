-- MySQL Workbench Forward Engineering
-- Bootstrap movie_library; CREATE TABLE IF NOT EXISTS does not migrate tables.
-- Users and the shared movie catalog are independent: there is no ownership FK.
-- Application request schemas enforce stricter username and movie-year rules.

SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;
SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';

-- -----------------------------------------------------
-- Schema movie_library
-- -----------------------------------------------------
CREATE SCHEMA IF NOT EXISTS `movie_library` ;
USE `movie_library` ;

-- -----------------------------------------------------
-- Table `movie_library`.`movies`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `movie_library`.`movies` (
  `id` INT(11) NOT NULL AUTO_INCREMENT,
  `title` VARCHAR(255) NOT NULL,
  `director` VARCHAR(255) NULL DEFAULT NULL,
  `release_year` SMALLINT(5) UNSIGNED NULL DEFAULT NULL,
  `rating` DECIMAL(4,2) NULL DEFAULT NULL,
  `rating_source` VARCHAR(50) NULL DEFAULT NULL,
  `rating_updated_at` DATETIME NULL DEFAULT NULL,
  `enrichment_error` VARCHAR(512) NULL DEFAULT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP() ON UPDATE CURRENT_TIMESTAMP(),
  PRIMARY KEY (`id`),
  INDEX `idx_movies_title` (`title` ASC) VISIBLE,
  INDEX `idx_movies_rating` (`rating` ASC) VISIBLE,
  INDEX `idx_movies_release_year` (`release_year` ASC) VISIBLE,
  UNIQUE INDEX `id_UNIQUE` (`id` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `movie_library`.`users`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `movie_library`.`users` (
  `id` INT(11) NOT NULL AUTO_INCREMENT,
  `username` VARCHAR(64) NOT NULL,
  `password_hash` VARCHAR(255) NOT NULL,
  `role` ENUM('ADMIN', 'USER') NOT NULL DEFAULT 'USER',
  `token_version` INT(11) NOT NULL DEFAULT 0,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_users_username` (`username` ASC) VISIBLE,
  UNIQUE INDEX `id_UNIQUE` (`id` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


SET SQL_MODE=@OLD_SQL_MODE;
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;
