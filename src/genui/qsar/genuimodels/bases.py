"""
genuimodels

Created by: Martin Sicho
On: 14-01-20, 10:16
"""
from abc import ABC, abstractmethod

from genui.utils.inspection import findSubclassByID, importFromPackage
from genui.compounds.models import Molecule, ActivityTypes, ActivitySet
from genui.models.genuimodels.bases import Algorithm, CompleteBuilder
from genui.qsar import models
import pandas as pd
from pandas import DataFrame, Series


class DescriptorCalculator(ABC):
    group_name = None

    def __init__(self, builder):
        self.builder = builder

    @abstractmethod
    def __call__(self, smiles) -> DataFrame:
        pass

    @classmethod
    def getDjangoModel(cls, corePackage, update=False) -> models.DescriptorGroup:
        if not cls.group_name:
            raise Exception('You have to specify a name for the descriptor group in its class "group_name" property')

        ret, ret_created = models.DescriptorGroup.objects.get_or_create(name=cls.group_name)

        # just return if we are not setting up a new instance
        if not ret_created and not update:
            return ret

        if corePackage:
            ret.corePackage = corePackage
            ret.save()

        return ret

class DescriptorBuilderMixIn:

    @staticmethod
    def findDescriptorClass(name, corePackage):
        module = importFromPackage(corePackage, "descriptors")
        return findSubclassByID(DescriptorCalculator, module, "group_name", name)

    def __init__(self, instance: models.Model, progress=None, onFitCall=None):
        super().__init__(instance, progress, onFitCall)
        self.molsets = [self.instance.molset] if hasattr(self.instance, "molset") else self.instance.molsets.all()
        self.descriptorClasses = [self.findDescriptorClass(x.name, x.corePackage) for x in self.training.descriptors.all()]

        self.X = None
        self.y = None

    def calculateDescriptors(self, mols=None):
        """
        Calculate descriptors for the given molecules
        and save them as X in this instance. If mols is None,
        the 'self.mols' or 'self.molsets' (in the order of pereference)
        attributes will be used to get molecules for the calculation.

        :param mols: List of molecules to save as X. Can be either instances of Molecule or smiles strings
        :return:
        """

        if mols is not None:
            smiles = [x.canonicalSMILES if isinstance(x, Molecule) else x for x in mols]
        elif hasattr(self, "mols"):
            smiles = [x.canonicalSMILES if isinstance(x, Molecule) else x for x in self.mols]
        elif hasattr(self, "molsets"):
            smiles = []
            for molset in self.molsets:
                for mol in molset.molecules.all():
                    smiles.append(mol.canonicalSMILES)
        else:
            raise Exception("No molecules to calculate descriptors from.")

        self.X = DataFrame()
        for desc_class in self.descriptorClasses:
            calculator = desc_class(self)
            temp = calculator(smiles)
            temp.columns = [f"{desc_class.group_name}_{x}" for x in temp.columns]
            self.X = pd.concat([self.X, temp], axis=1)
        return self.X

class QSARModelBuilder(DescriptorBuilderMixIn, CompleteBuilder):

    def getX(self) -> DataFrame:
        return self.X

    def getY(self) -> Series:
        return self.y

    def saveActivities(self):
        if not self.getY():
            activity_set = ActivitySet.objects.get(pk=self.training.activitySet.id)
            activity_type = self.training.activityType
            if not activity_set:
                raise Exception("No activity set specified.")
            if not activity_type:
                raise Exception("No activity type specified.")

            compounds, activities, units = activity_set.cleanForModelling(activity_type)
            if not len(compounds) == len(activities):
                raise Exception(f'Number of compounds in a QSAR model ({len(compounds)}) is different from the set of activities assigned to them ({len(activities)}). Something went wrong when the data was cleaned for modeling.')
            activities = Series(activities)

            # use the activity threshold for classifications
            if self.training.mode.name == Algorithm.CLASSIFICATION:
                activity_thrs = self.training.activityThreshold
                if activity_thrs is None:
                    raise Exception('No activity threshold specified for classification model.')
                activities = activities.apply(lambda x : 1 if x >= activity_thrs else 0)

                if not self.instance.predictionsType:
                    self.instance.predictionsType = ActivityTypes.objects.get_or_create(
                        value="Active Probability"
                    )[0]

            if not self.instance.predictionsType:
                self.instance.predictionsType = activity_type
            if not self.instance.predictionsUnits:
                self.instance.predictionsUnits = units

            self.instance.save()
            self.y = activities
            return self.y, compounds

    def populateActivitySet(self, aset : models.ModelActivitySet):
        raise NotImplementedError(f"Every QSAR model builder has to implement the {self.populateActivitySet.__name__} method.")
